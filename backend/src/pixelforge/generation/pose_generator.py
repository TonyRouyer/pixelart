"""Pose-guided animation frames: a whole grid at once, or one inpainted cell."""

from typing import Protocol

from PIL import Image

from pixelforge.comfy.client import ComfyClient
from pixelforge.config import Settings
from pixelforge.generation.base import (
    BACKGROUND_RGB,
    NEGATIVE_PROMPT,
    ProgressCallback,
    flatten,
    guard,
    run_workflow,
    sprite_prompt,
    upload,
)
from pixelforge.grid import cell_box, cell_size, compose_grid, split_grid
from pixelforge.poses.model import Pose
from pixelforge.poses.render import render_pose


class AnimationGenerator(Protocol):
    async def generate(
        self,
        ref: Image.Image,
        poses: list[Pose],
        style_prompt: str,
        seed: int,
        progress: ProgressCallback,
    ) -> list[Image.Image]: ...

    async def regenerate_frame(
        self,
        ref: Image.Image,
        poses: list[Pose],
        frames: list[Image.Image],
        index: int,
        style_prompt: str,
        seed: int,
        progress: ProgressCallback,
    ) -> Image.Image: ...


class PoseGenerator:
    def __init__(self, client: ComfyClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def _pose_grid(self, poses: list[Pose], cell: int) -> Image.Image:
        return compose_grid([render_pose(p, cell) for p in poses], cell)

    def _values(self, style_prompt: str, seed: int, ref_name: str, pose_name: str) -> dict:
        s = self.settings
        return {
            "checkpoint": s.checkpoint,
            "lora": s.lora,
            "lora_strength": s.lora_strength,
            "controlnet": s.controlnet_openpose,
            "ipadapter_preset": s.ipadapter_preset,
            "positive": sprite_prompt(style_prompt),
            "negative": NEGATIVE_PROMPT,
            "seed": seed,
            "reference_image": ref_name,
            "pose_image": pose_name,
        }

    async def generate(
        self,
        ref: Image.Image,
        poses: list[Pose],
        style_prompt: str,
        seed: int,
        progress: ProgressCallback,
    ) -> list[Image.Image]:
        n = len(poses)
        cell = cell_size(n, self.settings.grid_canvas)
        pose_grid = self._pose_grid(poses, cell)
        ref_name = await guard(upload(self.client, flatten(ref), "reference"))
        pose_name = await guard(upload(self.client, pose_grid, "pose"))
        values = {
            **self._values(style_prompt, seed, ref_name, pose_name),
            "width": pose_grid.width,
            "height": pose_grid.height,
            "batch": 1,
        }
        out = await run_workflow(self.client, "pose_grid", values, progress)
        grid = out[0].convert("RGBA").resize(pose_grid.size, Image.Resampling.NEAREST)
        return split_grid(grid, n)

    async def regenerate_frame(
        self,
        ref: Image.Image,
        poses: list[Pose],
        frames: list[Image.Image],
        index: int,
        style_prompt: str,
        seed: int,
        progress: ProgressCallback,
    ) -> Image.Image:
        n = len(poses)
        cell = cell_size(n, self.settings.grid_canvas)
        pose_grid = self._pose_grid(poses, cell)
        source = compose_grid([flatten(f) for f in frames], cell, BACKGROUND_RGB)
        mask = Image.new("RGB", source.size, (0, 0, 0))
        mask.paste((255, 255, 255), cell_box(index, n, cell))
        ref_name = await guard(upload(self.client, flatten(ref), "reference"))
        pose_name = await guard(upload(self.client, pose_grid, "pose"))
        source_name = await guard(upload(self.client, source, "source"))
        mask_name = await guard(upload(self.client, mask, "mask"))
        values = {
            **self._values(style_prompt, seed, ref_name, pose_name),
            "source_image": source_name,
            "mask_image": mask_name,
        }
        out = await run_workflow(self.client, "pose_inpaint", values, progress)
        grid = out[0].convert("RGBA").resize(source.size, Image.Resampling.NEAREST)
        return split_grid(grid, n)[index]
