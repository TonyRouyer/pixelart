"""Bundled pose library: per-view, per-animation, per-direction OpenPose clips."""

from importlib import resources
from importlib.resources.abc import Traversable

from pixelforge.domain.models import AnimationType, Direction, ViewKind
from pixelforge.poses.model import Pose, PoseClip

# COCO-18 right/left pairs: shoulders, elbows, wrists, hips, knees, ankles, eyes, ears.
_MIRROR_PAIRS: tuple[tuple[int, int], ...] = (
    (2, 5), (3, 6), (4, 7), (8, 11), (9, 12), (10, 13), (14, 15), (16, 17),
)  # fmt: skip
_MIRROR_INDEX: list[int] = list(range(18))
for _r, _l in _MIRROR_PAIRS:
    _MIRROR_INDEX[_r], _MIRROR_INDEX[_l] = _l, _r


def mirror_pose(pose: Pose) -> Pose:
    """Flip horizontally (x -> 1 - x) and swap each right/left joint pair."""
    flipped = [None if p is None else (1.0 - p[0], p[1]) for p in pose.points]
    return Pose(points=[flipped[i] for i in _MIRROR_INDEX])


def _view_dir(view: ViewKind) -> Traversable:
    return resources.files("pixelforge.poses").joinpath("data", view.value)


def load_clip(view: ViewKind, anim: AnimationType, direction: Direction) -> PoseClip:
    path = _view_dir(view).joinpath(anim.value, f"{direction.value}.json")
    return PoseClip.model_validate_json(path.read_text(encoding="utf-8"))


def load_neutral(view: ViewKind, direction: Direction) -> Pose:
    path = _view_dir(view).joinpath("neutral", f"{direction.value}.json")
    return Pose.model_validate_json(path.read_text(encoding="utf-8"))


def list_clips(view: ViewKind) -> list[tuple[AnimationType, Direction]]:
    root = _view_dir(view)
    return [
        (anim, direction)
        for anim in AnimationType
        for direction in Direction
        if root.joinpath(anim.value, f"{direction.value}.json").is_file()
    ]
