import asyncio
import json
from contextlib import aclosing

from fastapi import APIRouter, WebSocket

from pixelforge.api.deps import Bus

router = APIRouter()


@router.websocket("/ws")
async def events_socket(websocket: WebSocket, bus: Bus) -> None:
    """Forward every event of the bus as JSON text until the client disconnects."""
    async with aclosing(bus.subscribe()) as events:
        # start waiting before accepting so no event published after the handshake is missed
        pending = asyncio.ensure_future(events.__anext__())
        await websocket.accept()

        async def pump() -> None:
            nonlocal pending
            while True:
                event = await pending
                pending = asyncio.ensure_future(events.__anext__())
                await websocket.send_text(json.dumps(event))

        async def watch() -> None:
            while (await websocket.receive())["type"] != "websocket.disconnect":
                pass

        tasks = [asyncio.ensure_future(pump()), asyncio.ensure_future(watch())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (*tasks, pending):
                task.cancel()
            await asyncio.gather(*tasks, pending, return_exceptions=True)
