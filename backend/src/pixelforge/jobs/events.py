"""In-process pub/sub used to push job updates to connected clients."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

QUEUE_SIZE = 1000


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict]] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event: dict) -> None:
        """Deliver ``event`` to every subscriber, dropping a full queue's oldest event."""
        for q in self._subscribers:
            if q.full():
                q.get_nowait()
            q.put_nowait(event)

    async def subscribe(self) -> AsyncIterator[dict]:
        """Yield events published from the first iteration until the consumer stops."""
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subscribers.discard(q)
