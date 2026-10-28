"""Shared pieces of the ComfyUI-driven generators."""

from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

from PIL import Image

from pixelforge.comfy.client import ComfyClient, ComfyError
from pixelforge.comfy.workflows import bind, load_workflow

ProgressCallback = Callable[[float], None]

BACKGROUND_RGB = (210, 210, 210)
NEGATIVE_PROMPT = (
    "blurry, text, watermark, multiple characters per cell, cropped, background scenery"
)
SPRITE_SUFFIX = (
    "full body character, centered in each cell, consistent character design, "
    "plain flat light gray background"
)

_HINTS = {
    "gpu_oom": "Réduisez le nombre de frames, ou passez à un modèle SD 1.5 dans .env",
    "comfy_unreachable": "Lancez ComfyUI (run_nvidia_gpu.bat) puis réessayez",
}
_CODES = {
    "oom": "gpu_oom",
    "unreachable": "comfy_unreachable",
    "execution": "comfy_execution",
    "interrupted": "cancelled",
}


class GenerationError(Exception):
    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    @classmethod
    def from_comfy(cls, e: ComfyError) -> "GenerationError":
        code = _CODES[e.kind]
        return cls(code, e.message or str(e), _HINTS.get(code))


def flatten(img: Image.Image) -> Image.Image:
    """Alpha-composite onto the flat generation background, returning RGB."""
    rgba = img.convert("RGBA")
    canvas = Image.new("RGBA", rgba.size, BACKGROUND_RGB + (255,))
    return Image.alpha_composite(canvas, rgba).convert("RGB")


def sprite_prompt(style_or_prompt: str) -> str:
    return f"{style_or_prompt}, {SPRITE_SUFFIX}"


async def upload(client: ComfyClient, img: Image.Image, role: str) -> str:
    """Upload under a name unique to this call; return the server-side name."""
    return await client.upload_image(img, f"pf_{uuid4().hex}_{role}.png")


async def run_workflow(
    client: ComfyClient, name: str, values: dict, progress: ProgressCallback
) -> list[Image.Image]:
    try:
        return await client.run(bind(load_workflow(name), values), progress)
    except ComfyError as e:
        raise GenerationError.from_comfy(e) from e


_T = TypeVar("_T")


async def guard(call: Awaitable[_T]) -> _T:
    """Await ``call``, converting ComfyError (e.g. from uploads) to GenerationError."""
    try:
        return await call
    except ComfyError as e:
        raise GenerationError.from_comfy(e) from e
