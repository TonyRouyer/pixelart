"""Shared builders for export tests."""

from __future__ import annotations

from PIL import Image

from pixelforge.domain.models import (
    DIRECTION_ORDER,
    AnimationConfig,
    AnimationType,
    Direction,
    DirectionState,
    Project,
)

COLOR = {
    Direction.down: (255, 0, 0, 255),
    Direction.left: (0, 255, 0, 255),
    Direction.right: (0, 0, 255, 255),
    Direction.up: (255, 255, 0, 255),
}


def colored_frames(per_dir: int, size: int) -> dict[Direction, list[Image.Image]]:
    return {
        d: [Image.new("RGBA", (size, size), COLOR[d]) for _ in range(per_dir)]
        for d in DIRECTION_ORDER
    }


def anim(
    anim_id: str,
    fps: int = 10,
    loop: bool = True,
    frame_count: int = 6,
    statuses: dict[Direction, str] | None = None,
) -> AnimationConfig:
    statuses = statuses or {}
    return AnimationConfig(
        id=anim_id,
        type=AnimationType.walk,
        frame_count=frame_count,
        fps=fps,
        loop=loop,
        directions={
            d: DirectionState(
                status=statuses.get(d, "ready"),
                frames=[f"f{i}.png" for i in range(frame_count)]
                if statuses.get(d, "ready") != "empty"
                else [],
            )
            for d in DIRECTION_ORDER
        },
    )


def project_with(*animations: AnimationConfig, name: str = "Chevalier", size: int = 64) -> Project:
    return Project(id="p-1", name=name, seed=1, output_size=size, animations=list(animations))
