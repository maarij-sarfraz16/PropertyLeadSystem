"""The background scan worker.

Replaces `python -m app.scan ...` as the way leads enter the system. It starts with the API
process (FastAPI lifespan), scans every configured source on a fixed interval, and publishes
each new lead to the realtime broker.

Design decisions that make it production-safe:

- **Never blocks the event loop.** Scraping, Gemini calls and DB writes are synchronous and
  can take seconds. Each cycle runs in a worker thread via `asyncio.to_thread`, so FastAPI
  keeps serving requests at full speed while a scan is in flight.
- **Errors are survivable.** A failed cycle is logged, recorded on the source's scan state,
  and retried after an exponential backoff that decorrelates repeated failures from the
  normal cadence. The loop itself never dies — only a cancellation stops it.
- **Graceful shutdown.** Interval sleeps await a stop event rather than sleeping blindly, so
  shutdown is immediate instead of waiting out the interval. On cancellation the in-flight
  cycle is given a bounded window to finish so a half-written scan does not leak.
- **Bounded work.** One cycle handles at most `SCAN_MAX_NEW_PER_CYCLE` new listings; a burst
  of inventory spreads over cycles instead of stalling one long cycle.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import random
from typing import Any

from app.config import get_settings
from app.logging_config import get_logger
from app.notifications.matching import match_new_leads
from app.pipeline.ingest import ScanResult, record_scan_error, run_scan_cycle
from app.realtime.broker import Event, EventBroker, get_broker

log = get_logger(__name__)

# How long a cancelled worker may spend finishing its in-flight cycle before we stop waiting.
_SHUTDOWN_GRACE_SECONDS = 30.0


class ScanWorker:
    """Supervises one scan loop over the configured sources."""

    def __init__(self, broker: EventBroker | None = None) -> None:
        self._settings = get_settings()
        self._broker = broker or get_broker()
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._cycles = 0
        self._errors = 0
        self._total_new_leads = 0
        self._last_cycle_at: dt.datetime | None = None
        self._last_error: str | None = None
        self._running = False

    # -- lifecycle -----------------------------------------------------------
    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._run(), name="scan-worker")
        self._running = True
        log.info(
            "worker.started",
            extra={
                "sources": self._settings.scan_source_list,
                "interval_seconds": self._settings.scan_interval_seconds,
                "page_size": self._settings.scan_page_size,
                "max_new_per_cycle": self._settings.scan_max_new_per_cycle,
            },
        )

    async def stop(self) -> None:
        """Signal the loop, then wait briefly for the in-flight cycle to finish."""
        self._stop.set()
        self._running = False
        task = self._task
        if task is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=_SHUTDOWN_GRACE_SECONDS)
        except TimeoutError:
            log.warning("worker.shutdown_timeout", extra={"grace_seconds": _SHUTDOWN_GRACE_SECONDS})
            task.cancel()
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            pass
        finally:
            self._task = None
            log.info("worker.stopped", extra={"cycles": self._cycles, "errors": self._errors})

    @property
    def status(self) -> dict[str, Any]:
        """Snapshot for the /api/scan/status endpoint."""
        return {
            "running": self._running and self._task is not None and not self._task.done(),
            "enabled": self._settings.scan_enabled,
            "sources": self._settings.scan_source_list,
            "intervalSeconds": self._settings.scan_interval_seconds,
            "cycles": self._cycles,
            "errors": self._errors,
            "totalNewLeads": self._total_new_leads,
            "lastCycleAt": self._last_cycle_at.isoformat() if self._last_cycle_at else None,
            "lastError": self._last_error,
            "realtime": self._broker.stats,
        }

    # -- loop ----------------------------------------------------------------
    async def _run(self) -> None:
        try:
            await self._sleep(self._settings.scan_startup_delay_seconds)
            backoff = self._settings.scan_error_backoff_seconds

            while not self._stop.is_set():
                failed = False
                for source in self._settings.scan_source_list:
                    if self._stop.is_set():
                        break
                    ok = await self._scan_source(source)
                    failed = failed or not ok

                self._cycles += 1
                self._last_cycle_at = dt.datetime.now(dt.UTC)

                if failed:
                    delay = self._jitter(backoff)
                    log.warning(
                        "scan.retry_scheduled",
                        extra={
                            "delay_seconds": round(delay, 1),
                            "consecutive_errors": self._errors,
                        },
                    )
                    backoff = min(backoff * 2, self._settings.scan_error_backoff_max_seconds)
                else:
                    backoff = self._settings.scan_error_backoff_seconds
                    delay = self._settings.scan_interval_seconds

                await self._sleep(delay)
        except asyncio.CancelledError:
            log.info("worker.cancelled")
            raise
        except Exception:  # pragma: no cover - the loop must not die silently
            log.exception("worker.crashed")
            raise

    async def _scan_source(self, source: str) -> bool:
        """Run one cycle for one source off the event loop. Returns False on failure."""
        try:
            result: ScanResult = await asyncio.to_thread(run_scan_cycle, source)
        except Exception as exc:
            self._errors += 1
            self._last_error = f"{source}: {exc}"
            log.exception("scan.error", extra={"source": source, "error": str(exc)})
            await asyncio.to_thread(record_scan_error, source, str(exc))
            self._publish(Event("scan.error", {"source": source, "error": str(exc)}))
            return False

        self._total_new_leads += result.new_count
        self._last_error = None
        self._broadcast(result)
        await self._dispatch_alerts(result)
        return True

    async def _dispatch_alerts(self, result: ScanResult) -> None:
        """Match the cycle's new leads against saved searches and push any alerts.

        Deliberately swallows everything. The scraper is the product and alerting is a feature
        layered on top of it: a malformed saved search, a schema drift or a database hiccup
        must never turn a successful scan into a failed one. The cycle has already been
        broadcast and recorded by the time this runs.
        """
        if not self._settings.alerts_enabled or not result.new_leads:
            return
        try:
            lead_ids = [lead["id"] for lead in result.new_leads if lead.get("id")]
            alerts = await asyncio.to_thread(match_new_leads, lead_ids)
            for alert in alerts:
                if not alert.get("notifyRealtime"):
                    continue  # inbox-only search: recorded, but no toast
                self._publish(
                    Event("alert.created", {"alert": alert}, audience=_audience_for(alert))
                )
        except Exception:
            log.exception("alerts.dispatch_failed", extra={"source": result.source})

    # -- fan-out -------------------------------------------------------------
    def _broadcast(self, result: ScanResult) -> None:
        """Push the cycle's outcome to connected dashboards."""
        for lead in result.new_leads:
            self._publish(Event("lead.created", {"lead": lead}))

        self._publish(
            Event(
                "scan.completed",
                {
                    "source": result.source,
                    "fetched": result.fetched,
                    "newLeads": result.new_count,
                    "duplicates": result.duplicates,
                    "skippedSeen": result.skipped_seen,
                },
            )
        )

        if result.new_count:
            # Metrics and charts derive from aggregates the client must refetch; this is the
            # signal to do so, sent only when something actually changed.
            self._publish(Event("dashboard.updated", {"newLeads": result.new_count}))
            log.info(
                "dashboard.updated",
                extra={"new_leads": result.new_count, "subscribers": self._broker.subscriber_count},
            )

    def _publish(self, event: Event) -> None:
        """Publish from whichever context we are in (loop thread or worker thread)."""
        if self._loop is not None and self._loop.is_running():
            try:
                asyncio.get_running_loop()
                self._broker.publish(event)
            except RuntimeError:
                self._broker.publish_from_thread(self._loop, event)
        else:  # pragma: no cover - shutdown race
            self._broker.publish(event)

    # -- helpers -------------------------------------------------------------
    async def _sleep(self, seconds: float) -> None:
        """Interruptible sleep: returns immediately once shutdown is signalled."""
        if seconds <= 0:
            return
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except TimeoutError:
            pass

    @staticmethod
    def _jitter(delay: float) -> float:
        """Spread retries so repeated failures do not resynchronize into a thundering herd."""
        return delay * random.uniform(0.8, 1.2)


def _audience_for(alert: dict[str, Any]) -> frozenset[str]:
    """Topics an alert should reach: its saved search, and its agent if it has one.

    A client that names no topics still receives it — targeting narrows opt-in only, which is
    the correct default for a shared instance with no authentication.
    """
    topics = {f"search:{alert['savedSearchId']}"}
    if alert.get("agentId"):
        topics.add(f"agent:{alert['agentId']}")
    return frozenset(topics)


_worker: ScanWorker | None = None


def get_worker() -> ScanWorker:
    global _worker
    if _worker is None:
        _worker = ScanWorker()
    return _worker
