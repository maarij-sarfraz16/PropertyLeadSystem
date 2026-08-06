"""In-process publish/subscribe for dashboard events.

The worker and the API run in one process, so a plain asyncio broker delivers events with no
extra infrastructure. Two properties matter for a service that must stay up for weeks:

**Bounded memory.** Each subscriber gets its own fixed-size queue. A browser tab that is
suspended or on a slow link stops draining; rather than growing that queue without limit, the
broker drops the oldest event and counts the drop. Lag costs a client stale events, never the
server's memory.

**Non-blocking publish.** `publish` never awaits a slow consumer, so a stalled WebSocket
cannot slow the scan pipeline or a request handler.

The subscriber interface is deliberately transport-agnostic: the WebSocket and SSE endpoints
are two renderings of the same stream. Scaling past one process means swapping this class for
a Redis pub/sub implementation behind the same two methods — `redis_url` is already configured.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.logging_config import get_logger

log = get_logger(__name__)


@dataclass
class Event:
    """One dashboard event. `type` is the client-side discriminator.

    `audience` is routing metadata, not payload: it never reaches the wire. `None` means
    broadcast, which is what every pre-existing event uses.
    """

    type: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
    audience: frozenset[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "ts": self.ts, "data": self.data}


class EventBroker:
    def __init__(self, queue_size: int | None = None) -> None:
        self._queue_size = queue_size or get_settings().realtime_queue_size
        # Queue -> the topics that subscriber cares about; None means "everything".
        self._subscribers: dict[asyncio.Queue[Event], frozenset[str] | None] = {}
        self._lock = asyncio.Lock()
        self._published = 0
        self._dropped = 0

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @property
    def stats(self) -> dict[str, int]:
        return {
            "subscribers": len(self._subscribers),
            "published": self._published,
            "dropped": self._dropped,
        }

    def publish(self, event: Event) -> None:
        """Fan an event out to every interested subscriber. Never blocks, never raises."""
        self._published += 1
        for queue, topics in list(self._subscribers.items()):
            if self._delivers(event, topics):
                self._offer(queue, event)

    @staticmethod
    def _delivers(event: Event, topics: frozenset[str] | None) -> bool:
        """Whether a subscriber watching `topics` should receive `event`.

        Targeting narrows opt-*in*, never opt-out: an event with no audience still reaches
        everyone, and a subscriber that named no topics still receives everything. Both
        defaults preserve the pre-targeting behaviour exactly.

        Note this is a routing convenience, not a security boundary — there is no auth, and a
        client may name any topic it likes. It exists so the dashboard can scope toasts to one
        agent without filtering a firehose client-side, and it is the seam auth would plug into.
        """
        if event.audience is None:
            return True
        if topics is None:
            return True
        return bool(event.audience & topics)

    def publish_from_thread(self, loop: asyncio.AbstractEventLoop, event: Event) -> None:
        """Publish from a worker thread onto the API's event loop.

        The scan pipeline is synchronous and runs in a thread; asyncio queues are not
        thread-safe, so the hop back onto the loop has to be explicit.
        """
        try:
            loop.call_soon_threadsafe(self.publish, event)
        except RuntimeError:  # loop already closed during shutdown
            log.debug("realtime.publish_after_close", extra={"event": event.type})

    def _offer(self, queue: asyncio.Queue[Event], event: Event) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # Shed the oldest event so a lagging client sees recent state, not ancient state.
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
            self._dropped += 1
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    @contextlib.asynccontextmanager
    async def subscribe(
        self, topics: Iterable[str] | None = None
    ) -> AsyncIterator[asyncio.Queue[Event]]:
        """Register a subscriber for the duration of the context.

        `topics` narrows which targeted events reach this subscriber; omitting it (the
        default) delivers everything, which is what every caller did before targeting existed.

        Unsubscribing in `finally` is what keeps a long-lived server leak-free: every dropped
        connection releases its queue, whether it closed cleanly, errored, or was cancelled.
        """
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._queue_size)
        wanted = frozenset(topics) if topics is not None else None
        async with self._lock:
            self._subscribers[queue] = wanted
        log.debug("realtime.subscribed", extra={"subscribers": len(self._subscribers)})
        try:
            yield queue
        finally:
            async with self._lock:
                self._subscribers.pop(queue, None)
            log.debug("realtime.unsubscribed", extra={"subscribers": len(self._subscribers)})


_broker: EventBroker | None = None


def get_broker() -> EventBroker:
    """Process-wide broker shared by the worker and every connected client."""
    global _broker
    if _broker is None:
        _broker = EventBroker()
    return _broker
