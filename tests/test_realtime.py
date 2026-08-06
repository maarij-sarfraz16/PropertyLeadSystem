"""Event broker: fan-out, bounded memory, and subscriber cleanup."""
from __future__ import annotations

import asyncio

import pytest

from app.realtime.broker import Event, EventBroker


@pytest.mark.asyncio
async def test_event_reaches_every_subscriber():
    broker = EventBroker(queue_size=10)
    async with broker.subscribe() as first, broker.subscribe() as second:
        broker.publish(Event("lead.created", {"lead": {"id": "abc"}}))
        assert (await first.get()).data["lead"]["id"] == "abc"
        assert (await second.get()).data["lead"]["id"] == "abc"


@pytest.mark.asyncio
async def test_subscriber_is_removed_on_exit():
    """The leak guard: every closed connection must release its queue."""
    broker = EventBroker(queue_size=4)
    async with broker.subscribe():
        assert broker.subscriber_count == 1
    assert broker.subscriber_count == 0


@pytest.mark.asyncio
async def test_subscriber_is_removed_even_when_the_consumer_raises():
    broker = EventBroker(queue_size=4)
    with pytest.raises(RuntimeError):
        async with broker.subscribe():
            raise RuntimeError("client blew up")
    assert broker.subscriber_count == 0


@pytest.mark.asyncio
async def test_lagging_subscriber_drops_oldest_instead_of_growing():
    """A stalled client costs itself stale events, never the server's memory."""
    broker = EventBroker(queue_size=3)
    async with broker.subscribe() as queue:
        for index in range(10):
            broker.publish(Event("lead.created", {"n": index}))

        assert queue.qsize() == 3
        received = [(await queue.get()).data["n"] for _ in range(3)]
        # The three most recent survived; the older seven were shed.
        assert received == [7, 8, 9]
        assert broker.stats["dropped"] == 7


@pytest.mark.asyncio
async def test_publish_with_no_subscribers_is_harmless():
    broker = EventBroker(queue_size=2)
    broker.publish(Event("scan.completed", {"newLeads": 0}))
    assert broker.stats["published"] == 1


@pytest.mark.asyncio
async def test_publish_from_thread_hops_onto_the_loop():
    """The worker runs scans in a thread; asyncio queues are not thread-safe."""
    broker = EventBroker(queue_size=5)
    loop = asyncio.get_running_loop()
    async with broker.subscribe() as queue:
        await asyncio.to_thread(
            broker.publish_from_thread, loop, Event("lead.created", {"lead": {"id": "z"}})
        )
        event = await asyncio.wait_for(queue.get(), timeout=2)
        assert event.data["lead"]["id"] == "z"


def test_event_serializes_with_type_and_timestamp():
    payload = Event("lead.created", {"lead": {"id": "1"}}).to_dict()
    assert payload["type"] == "lead.created"
    assert payload["data"]["lead"]["id"] == "1"
    assert payload["ts"]


# -- targeted delivery --------------------------------------------------------
# Targeting narrows opt-in only. Both defaults below (no audience, no topics) must behave
# exactly as they did before targeting existed — the tests above are the compatibility proof,
# and these pin the new behaviour.


@pytest.mark.asyncio
async def test_broadcast_still_reaches_a_topic_subscriber():
    """An event with no audience goes everywhere, however narrowly a client subscribed."""
    broker = EventBroker(queue_size=10)
    async with broker.subscribe(topics=["search:a"]) as queue:
        broker.publish(Event("scan.completed", {"newLeads": 2}))
        assert (await queue.get()).type == "scan.completed"


@pytest.mark.asyncio
async def test_targeted_event_reaches_only_the_matching_topic():
    broker = EventBroker(queue_size=10)
    async with broker.subscribe(topics=["search:a"]) as wanted, broker.subscribe(
        topics=["search:b"]
    ) as other:
        broker.publish(Event("alert.created", {"alert": {"id": "1"}}, audience=frozenset({"search:a"})))

        assert (await wanted.get()).data["alert"]["id"] == "1"
        assert other.empty()


@pytest.mark.asyncio
async def test_untargeted_subscriber_receives_targeted_events():
    """The shared-instance default: naming no topics means "show me everything"."""
    broker = EventBroker(queue_size=10)
    async with broker.subscribe() as queue:
        broker.publish(Event("alert.created", {"alert": {"id": "1"}}, audience=frozenset({"search:a"})))
        assert (await queue.get()).data["alert"]["id"] == "1"


@pytest.mark.asyncio
async def test_audience_is_routing_metadata_and_never_reaches_the_wire():
    event = Event("alert.created", {"alert": {"id": "1"}}, audience=frozenset({"search:a"}))
    assert "audience" not in event.to_dict()


@pytest.mark.asyncio
async def test_subscriber_matching_any_one_topic_receives_the_event():
    broker = EventBroker(queue_size=10)
    async with broker.subscribe(topics=["agent:me", "search:other"]) as queue:
        broker.publish(
            Event("alert.created", {}, audience=frozenset({"search:x", "agent:me"}))
        )
        assert (await queue.get()).type == "alert.created"
