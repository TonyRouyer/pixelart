"""In-memory ComfyUI stand-in for tests and GPU-less development."""

from collections.abc import Callable

from PIL import Image

from pixelforge.comfy.workflows import all_required_nodes
from pixelforge.config import Settings


class FakeComfyClient:
    def __init__(
        self,
        responder: Callable[[dict], list[Image.Image]],
        object_info: dict | None = None,
        models: dict[str, list[str]] | None = None,
    ) -> None:
        self.responder = responder
        if object_info is None:
            object_info = {name: {} for name in sorted(all_required_nodes())}
        if models is None:
            s = Settings()
            models = {
                "checkpoints": [s.checkpoint],
                "loras": [s.lora],
                "controlnet": [s.controlnet_openpose],
            }
        self._object_info = object_info
        self._models = models
        self.workflows: list[dict] = []
        self.uploads: dict[str, Image.Image] = {}
        self.interrupted = False

    async def upload_image(self, img: Image.Image, name: str) -> str:
        self.uploads[name] = img
        return name

    async def run(self, workflow: dict, on_progress: Callable[[float], None]) -> list[Image.Image]:
        images = self.responder(workflow)
        self.workflows.append(workflow)
        on_progress(1.0)
        return images

    async def interrupt(self) -> None:
        self.interrupted = True

    async def object_info(self) -> dict:
        return self._object_info

    async def models(self, folder: str) -> list[str]:
        return self._models.get(folder, [])
