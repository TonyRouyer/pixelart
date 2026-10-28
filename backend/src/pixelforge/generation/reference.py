"""Reference-image generation: concept art, background removal, directional turnaround."""

from typing import Protocol

from PIL import Image

from pixelforge.comfy.client import ComfyClient
from pixelforge.config import Settings
from pixelforge.domain.models import DIRECTION_ORDER, Direction, ViewKind
from pixelforge.generation.base import (
    NEGATIVE_PROMPT,
    flatten,
    guard,
    run_workflow,
    sprite_prompt,
    upload,
)
from pixelforge.grid import cell_size, compose_grid, split_grid
from pixelforge.poses.library import load_neutral
from pixelforge.poses.render import render_pose

REFERENCE_SIZE = 1024


class ReferenceGenerator(Protocol):
    async def from_prompt(self, prompt: str, n: int, seed: int) -> list[Image.Image]: ...

    async def remove_background(self, img: Image.Image) -> Image.Image: ...

    async def turnaround(
        self, reference: Image.Image, view: ViewKind, seed: int
    ) -> dict[Direction, Image.Image]: ...


class ComfyReferenceGenerator:
    def __init__(self, client: ComfyClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def _model_values(self) -> dict:
        s = self.settings
        return {"checkpoint": s.checkpoint, "lora": s.lora, "lora_strength": s.lora_strength}

    async def from_prompt(self, prompt: str, n: int = 4, seed: int = 0) -> list[Image.Image]:
        values = {
            **self._model_values(),
            "positive": sprite_prompt(prompt),
            "negative": NEGATIVE_PROMPT,
            "seed": seed,
            "width": REFERENCE_SIZE,
            "height": REFERENCE_SIZE,
            "batch": n,
        }
        return await run_workflow(self.client, "txt2img", values, lambda p: None)

    async def remove_background(self, img: Image.Image) -> Image.Image:
        name = await guard(upload(self.client, img.convert("RGBA"), "source"))
        out = await run_workflow(self.client, "remove_bg", {"source_image": name}, lambda p: None)
        return out[0].convert("RGBA")

    async def turnaround(
        self, reference: Image.Image, view: ViewKind, seed: int
    ) -> dict[Direction, Image.Image]:
        n = len(DIRECTION_ORDER)
        cell = cell_size(n, self.settings.grid_canvas)
        poses = [render_pose(load_neutral(view, d), cell) for d in DIRECTION_ORDER]
        pose_grid = compose_grid(poses, cell)
        ref_name = await guard(upload(self.client, flatten(reference), "reference"))
        pose_name = await guard(upload(self.client, pose_grid, "pose"))
        s = self.settings
        values = {
            **self._model_values(),
            "controlnet": s.controlnet_openpose,
            "ipadapter_preset": s.ipadapter_preset,
            "positive": sprite_prompt("pixel art character turnaround"),
            "negative": NEGATIVE_PROMPT,
            "seed": seed,
            "width": pose_grid.width,
            "height": pose_grid.height,
            "batch": 1,
            "reference_image": ref_name,
            "pose_image": pose_name,
        }
        out = await run_workflow(self.client, "turnaround", values, lambda p: None)
        grid = out[0].convert("RGBA").resize(pose_grid.size, Image.Resampling.NEAREST)
        return dict(zip(DIRECTION_ORDER, split_grid(grid, n), strict=True))
