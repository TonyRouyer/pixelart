import asyncio
from contextlib import aclosing

from pixelforge.jobs.events import EventBus

TIMEOUT = 2


async def _until_subscribed(bus: EventBus, count: int) -> None:
    async def poll() -> None:
        while bus.subscriber_count < count:
            await asyncio.sleep(0)

    await asyncio.wait_for(poll(), TIMEOUT)


async def test_subscriber_receives_events_in_order():
    bus = EventBus()
    received: list[dict] = []

    async def consume() -> None:
        async for event in bus.subscribe():
            received.append(event)
            if len(received) == 2:
                return

    task = asyncio.create_task(consume())
    await _until_subscribed(bus, 1)
    bus.publish({"n": 1})
    bus.publish({"n": 2})
    await asyncio.wait_for(task, TIMEOUT)
    assert received == [{"n": 1}, {"n": 2}]


async def test_every_subscriber_gets_every_event():
    bus = EventBus()
    results: list[list[dict]] = [[], []]

    async def consume(out: list[dict]) -> None:
        async for event in bus.subscribe():
            out.append(event)
            return

    tasks = [asyncio.create_task(consume(out)) for out in results]
    await _until_subscribed(bus, 2)
    bus.publish({"n": 1})
    await asyncio.wait_for(asyncio.gather(*tasks), TIMEOUT)
    assert results == [[{"n": 1}], [{"n": 1}]]


async def test_unsubscribes_when_consumer_stops():
    bus = EventBus()

    async def consume() -> None:
        async with aclosing(bus.subscribe()) as events:
            async for _ in events:
                return

    task = asyncio.create_task(consume())
    await _until_subscribed(bus, 1)
    bus.publish({"n": 1})
    await asyncio.wait_for(task, TIMEOUT)
    assert bus.subscriber_count == 0


async def test_unsubscribes_when_consumer_cancelled():
    bus = EventBus()

    async def consume() -> None:
        async for _ in bus.subscribe():
            pass

    task = asyncio.create_task(consume())
    await _until_subscribed(bus, 1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert bus.subscriber_count == 0


async def test_publish_without_subscribers_is_noop():
    EventBus().publish({"n": 1})


async def test_full_queue_drops_oldest():
    bus = EventBus()
    received: list[int] = []

    async def consume() -> None:
        async for event in bus.subscribe():
            received.append(event["n"])
            if event["n"] == 1099:
                return

    task = asyncio.create_task(consume())
    await _until_subscribed(bus, 1)
    for n in range(1100):  # no await: the consumer cannot drain while we publish
        bus.publish({"n": n})
    await asyncio.wait_for(task, TIMEOUT)
    assert len(received) == 1000
    assert received[0] == 100
    assert received[-1] == 1099
