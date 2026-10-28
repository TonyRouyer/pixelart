"""Pose, keyframes and clip interpolation (OpenPose COCO-18 layout)."""

from itertools import pairwise
from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator

Coord = Annotated[float, Field(ge=0.0, le=1.0)]
Point = tuple[Coord, Coord] | None
Points = Annotated[list[Point], Field(min_length=18, max_length=18)]


class Pose(BaseModel):
    points: Points


class Keyframe(BaseModel):
    t: Annotated[float, Field(ge=0.0, le=1.0)]
    points: Points


class PoseClip(BaseModel):
    loop: bool
    keyframes: Annotated[list[Keyframe], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_times(self) -> Self:
        ts = [k.t for k in self.keyframes]
        if ts[0] != 0:
            raise ValueError("first keyframe must have t == 0")
        if any(b < a for a, b in pairwise(ts)):
            raise ValueError("keyframes must be sorted by t")
        return self


def _lerp_point(a: Point, b: Point, u: float) -> Point:
    if a is None or b is None:
        return None
    return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)


def _pose_at(clip: PoseClip, t: float) -> Pose:
    frames = clip.keyframes
    if clip.loop:
        # The segment after the last keyframe interpolates toward the first one at t = 1.
        frames = [*frames, Keyframe(t=1.0, points=frames[0].points)]
    for a, b in pairwise(frames):
        if t <= b.t:
            span = b.t - a.t
            u = 0.0 if span <= 0 else min(1.0, max(0.0, (t - a.t) / span))
            return Pose(points=[_lerp_point(p, q, u) for p, q in zip(a.points, b.points)])
    return Pose(points=list(frames[-1].points))


def sample(clip: PoseClip, n: int) -> list[Pose]:
    if clip.loop:
        times = [i / n for i in range(n)]
    else:
        times = [i / (n - 1) if n > 1 else 0.0 for i in range(n)]
    return [_pose_at(clip, t) for t in times]
