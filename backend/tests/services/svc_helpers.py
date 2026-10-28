"""Helpers shared by the service tests."""

import asyncio
import zipfile

from pixelforge.comfy.sprite_fake import SpriteFakeComfyClient

TIMEOUT = 5


class BlockingClient(SpriteFakeComfyClient):
    """Sprite fake whose generations wait for ``gate`` to open."""

    def __init__(self) -> None:
        super().__init__()
        self.gate = asyncio.Event()
        self.started = asyncio.Event()

    async def run(self, workflow, on_progress):
        self.started.set()
        await self.gate.wait()
        return await super().run(workflow, on_progress)


def zip_names(storage, key: str) -> list[str]:
    with zipfile.ZipFile(storage.path(key)) as z:
        return z.namelist()
