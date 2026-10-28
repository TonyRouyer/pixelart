"""Domain models for a PixelForge project."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class Direction(StrEnum):
    down = "down"
    left = "left"
    right = "right"
    up = "up"


DIRECTION_ORDER: tuple[Direction, ...] = (
    Direction.down,
    Direction.left,
    Direction.right,
    Direction.up,
)


class ViewKind(StrEnum):
    topdown4 = "topdown4"


class AnimationType(StrEnum):
    idle = "idle"
    walk = "walk"
    attack_unarmed = "attack_unarmed"
    attack_sword = "attack_sword"
    attack_spear = "attack_spear"
    attack_bow = "attack_bow"


class AnimationDefaults(BaseModel):
    frame_count: int
    fps: int
    loop: bool


DEFAULT_ANIMATIONS: dict[AnimationType, AnimationDefaults] = {
    AnimationType.idle: AnimationDefaults(frame_count=4, fps=6, loop=True),
    AnimationType.walk: AnimationDefaults(frame_count=6, fps=10, loop=True),
    AnimationType.attack_unarmed: AnimationDefaults(frame_count=6, fps=12, loop=False),
    AnimationType.attack_sword: AnimationDefaults(frame_count=6, fps=12, loop=False),
    AnimationType.attack_spear: AnimationDefaults(frame_count=6, fps=12, loop=False),
    AnimationType.attack_bow: AnimationDefaults(frame_count=6, fps=12, loop=False),
}


class PaletteSettings(BaseModel):
    mode: Literal["auto", "preset", "custom"] = "auto"
    colors: int = Field(default=24, ge=2, le=64)
    preset: str | None = None
    custom_colors: list[str] | None = None

    @field_validator("custom_colors")
    @classmethod
    def _check_hex(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for c in v:
                if not _HEX_COLOR.match(c):
                    raise ValueError(f"invalid hex color: {c!r}")
        return v

    @model_validator(mode="after")
    def _check_mode(self) -> PaletteSettings:
        if self.mode == "preset" and not self.preset:
            raise ValueError("preset is required when mode='preset'")
        if self.mode == "custom" and (not self.custom_colors or len(self.custom_colors) < 2):
            raise ValueError("custom_colors (at least 2) required when mode='custom'")
        return self


class OutlineSettings(BaseModel):
    enabled: bool = False
    color: str = "#1a1a1a"


class PixelSettings(BaseModel):
    palette: PaletteSettings = Field(default_factory=PaletteSettings)
    outline: OutlineSettings = Field(default_factory=OutlineSettings)
    alpha_threshold: int = Field(default=128, ge=0, le=255)
    padding: int = Field(default=0, ge=0)


class DirectionState(BaseModel):
    frames: list[str] = Field(default_factory=list)
    status: Literal["empty", "generating", "ready", "stale"] = "empty"


class AnimationConfig(BaseModel):
    id: str
    type: AnimationType
    frame_count: int = Field(ge=2, le=16)
    fps: int = Field(ge=1, le=60)
    loop: bool
    directions: dict[Direction, DirectionState]

    @field_validator("directions")
    @classmethod
    def _all_directions(cls, v: dict[Direction, DirectionState]) -> dict[Direction, DirectionState]:
        if set(v) != set(DIRECTION_ORDER):
            raise ValueError("directions must contain exactly down, left, right, up")
        # normalize to canonical order
        return {d: v[d] for d in DIRECTION_ORDER}

    @classmethod
    def from_type(cls, t: AnimationType) -> AnimationConfig:
        d = DEFAULT_ANIMATIONS[t]
        return cls(
            id=t.value,
            type=t,
            frame_count=d.frame_count,
            fps=d.fps,
            loop=d.loop,
            directions={dr: DirectionState() for dr in DIRECTION_ORDER},
        )


class ReferenceState(BaseModel):
    status: Literal["none", "candidates", "validated"] = "none"
    candidates: list[str] = Field(default_factory=list)


ViewStatus = Literal["pending", "generated", "validated"]


def _pending_views() -> dict[Direction, ViewStatus]:
    return {d: "pending" for d in DIRECTION_ORDER}


class Project(BaseModel):
    id: str
    name: str
    view: ViewKind = ViewKind.topdown4
    style_prompt: str = "pixel art, 16-bit rpg character, top-down view"
    seed: int
    output_size: int = Field(default=64, ge=16, le=256)
    pixel_settings: PixelSettings = Field(default_factory=PixelSettings)
    reference: ReferenceState = Field(default_factory=ReferenceState)
    views: dict[Direction, ViewStatus] = Field(default_factory=_pending_views)
    mirror_right: bool = False
    animations: list[AnimationConfig] = Field(default_factory=list)

    def animation(self, anim_id: str) -> AnimationConfig:
        for a in self.animations:
            if a.id == anim_id:
                return a
        raise KeyError(anim_id)

    def anchor(self) -> tuple[int, int]:
        return (self.output_size // 2, self.output_size - max(1, self.output_size // 16))
