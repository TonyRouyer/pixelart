"""Preview the pose library as skeleton grids, and generate left/*.json from right/*.json.

Usage (from backend/):
    python tools/preview_poses.py walk --frames 6
    python tools/preview_poses.py walk --mirror right     # rewrite walk/left.json, then preview
    python tools/preview_poses.py --mirror right          # rewrite left.json of every clip
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

import pixelforge.poses as poses_pkg
from pixelforge.domain.models import DIRECTION_ORDER, AnimationType, Direction, ViewKind
from pixelforge.poses.library import load_clip, load_neutral, mirror_pose
from pixelforge.poses.model import Keyframe, Pose, PoseClip, sample
from pixelforge.poses.render import render_pose

DATA_DIR = Path(poses_pkg.__file__).parent / "data" / ViewKind.topdown4.value
PREVIEW_DIR = Path(__file__).resolve().parents[1] / "data" / "pose_previews"
CELL = 256


def _write_json(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload + "\n", encoding="utf-8")


def write_mirrored(anim: AnimationType) -> None:
    """Write <anim>/left.json as the exact mirror of <anim>/right.json."""
    right = load_clip(ViewKind.topdown4, anim, Direction.right)
    left = PoseClip(
        loop=right.loop,
        keyframes=[
            Keyframe(t=k.t, points=mirror_pose(Pose(points=k.points)).points)
            for k in right.keyframes
        ],
    )
    _write_json(DATA_DIR / anim.value / "left.json", left.model_dump_json())


def write_mirrored_neutral() -> None:
    neutral = mirror_pose(load_neutral(ViewKind.topdown4, Direction.right))
    _write_json(DATA_DIR / "neutral" / "left.json", neutral.model_dump_json())


def render_preview(anim: AnimationType, frames: int) -> Path:
    """One row per direction, one column per sampled frame."""
    sheet = Image.new("RGB", (frames * CELL, len(DIRECTION_ORDER) * CELL))
    draw = ImageDraw.Draw(sheet)
    for row, direction in enumerate(DIRECTION_ORDER):
        clip = load_clip(ViewKind.topdown4, anim, direction)
        for col, pose in enumerate(sample(clip, frames)):
            sheet.paste(render_pose(pose, CELL), (col * CELL, row * CELL))
            draw.text((col * CELL + 4, row * CELL + 4), f"{direction.value} {col}", fill="white")
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    out = PREVIEW_DIR / f"{anim.value}.png"
    sheet.save(out)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("anim", nargs="?", type=AnimationType)
    parser.add_argument("--frames", type=int, default=6)
    parser.add_argument("--mirror", choices=["right"], help="regenerate left/*.json from right")
    args = parser.parse_args()

    anims = [args.anim] if args.anim else list(AnimationType)
    if args.mirror:
        for anim in anims:
            write_mirrored(anim)
        if args.anim is None:
            write_mirrored_neutral()
    if args.anim is None and not args.mirror:
        parser.error("an animation is required unless --mirror is given")
    for anim in anims if args.anim else []:
        print(render_preview(anim, args.frames))


if __name__ == "__main__":
    main()
