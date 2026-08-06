"""Realtime transports for the dashboard.

WebSocket (`/ws/leads`) is the primary channel — bidirectional, low overhead, and it lets the
client answer heartbeats so a half-open connection is detected instead of lingering.

SSE (`/api/stream`) serves the same events for environments where a proxy will not upgrade a
WebSocket. Both read from one broker, so neither transport can fall behind the other.

Both send periodic heartbeats. Idle proxies close silent connections after 30-60s, and a
lead-detection system can legitimately be silent for minutes.
"""
from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.logging_config import get_logger
from app.realtime.broker import Event, get_broker

log = get_logger(__name__)

router = APIRouter()


def _topics(raw: str | None) -> list[str] | None:
    """Parse `?topics=agent:a,search:b` into a topic list, or None for "everything".

    Accepts the same comma-joined form the leads filters use. Omitting the parameter keeps the
    pre-targeting behaviour: the subscriber receives every event.
    """
    if raw is None:
        return None
    topics = [part.strip() for part in raw.split(",") if part.strip()]
    return topics or None


@router.websocket("/ws/leads")
async def leads_websocket(websocket: WebSocket, topics: str | None = None) -> None:
    """Stream lead and scan events to one dashboard client."""
    await websocket.accept()
    settings = get_settings()
    broker = get_broker()

    async with broker.subscribe(_topics(topics)) as queue:
        await websocket.send_text(json.dumps(Event("connected", broker.stats).to_dict()))
        log.info("realtime.ws_connected", extra={"subscribers": broker.subscriber_count})

        # Draining the client's inbound frames concurrently is what makes a closed tab
        # detectable: without it, a disconnect is only noticed on the next outbound send,
        # which may be minutes away.
        reader = asyncio.create_task(_drain(websocket))
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=settings.realtime_heartbeat_seconds
                    )
                except TimeoutError:
                    event = Event("heartbeat")
                if reader.done():
                    break
                await websocket.send_text(json.dumps(event.to_dict(), default=str))
        except (WebSocketDisconnect, RuntimeError, ConnectionError):
            pass
        finally:
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await reader
            log.info("realtime.ws_disconnected", extra={"subscribers": broker.subscriber_count - 1})


async def _drain(websocket: WebSocket) -> None:
    """Consume inbound frames until the client goes away."""
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        return


@router.get("/api/stream")
async def leads_sse(request: Request, topics: str | None = None) -> StreamingResponse:
    """Server-Sent Events fallback carrying the same event stream as the WebSocket."""
    settings = get_settings()
    broker = get_broker()
    wanted = _topics(topics)

    async def event_source():
        async with broker.subscribe(wanted) as queue:
            log.info("realtime.sse_connected", extra={"subscribers": broker.subscriber_count})
            yield _sse(Event("connected", broker.stats))
            try:
                while True:
                    # Disconnect detection for SSE is polled: there is no inbound channel.
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(
                            queue.get(), timeout=settings.realtime_heartbeat_seconds
                        )
                    except TimeoutError:
                        event = Event("heartbeat")
                    yield _sse(event)
            except asyncio.CancelledError:  # pragma: no cover - client hung up
                raise
            finally:
                log.info(
                    "realtime.sse_disconnected",
                    extra={"subscribers": broker.subscriber_count - 1},
                )

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Tell nginx not to buffer, or events arrive in batches instead of instantly.
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: Event) -> str:
    return f"event: {event.type}\ndata: {json.dumps(event.to_dict(), default=str)}\n\n"
