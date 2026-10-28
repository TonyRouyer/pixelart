import pytest

from pixelforge.domain.models import AnimationType, Direction, ViewKind
from pixelforge.poses.library import list_clips, load_clip, load_neutral, mirror_pose
from pixelforge.poses.model import Pose

ANIMS = list(AnimationType)
DIRS = list(Direction)


@pytest.mark.parametrize("anim", ANIMS)
@pytest.mark.parametrize("d", DIRS)
def test_clip_valid(anim, d):
    clip = load_clip(ViewKind.topdown4, anim, d)
    assert clip.keyframes[0].t == 0.0
    assert all(len(k.points) == 18 for k in clip.keyframes)
    assert all(0 <= c <= 1 for k in clip.keyframes for p in k.points if p for c in p)
    assert clip.loop == (anim in (AnimationType.idle, AnimationType.walk))


@pytest.mark.parametrize("anim", ANIMS)
def test_left_is_mirror_of_right(anim):
    right = load_clip(ViewKind.topdown4, anim, Direction.right)
    left = load_clip(ViewKind.topdown4, anim, Direction.left)
    assert left.loop == right.loop
    assert [k.t for k in left.keyframes] == [k.t for k in right.keyframes]
    for kl, kr in zip(left.keyframes, right.keyframes, strict=True):
        expected = mirror_pose(Pose(points=kr.points)).points
        for a, b in zip(kl.points, expected, strict=True):
            if b is None:
                assert a is None
            else:
                assert a == pytest.approx(b, abs=1e-6)


def test_mirror_pose_swaps_pairs_and_flips_x():
    pts = [None] * 18
    pts[2] = (0.25, 0.5)  # r_shoulder
    pts[14] = (0.4, 0.1)  # r_eye
    mirrored = mirror_pose(Pose(points=pts)).points
    assert mirrored[5] == pytest.approx((0.75, 0.5))
    assert mirrored[15] == pytest.approx((0.6, 0.1))
    assert mirrored[2] is None and mirrored[14] is None


def test_up_has_no_face():
    assert (
        load_clip(ViewKind.topdown4, AnimationType.idle, Direction.up).keyframes[0].points[0]
        is None
    )


@pytest.mark.parametrize("anim", ANIMS)
def test_up_never_shows_face(anim):
    clip = load_clip(ViewKind.topdown4, anim, Direction.up)
    for k in clip.keyframes:
        assert all(k.points[i] is None for i in (0, 14, 15, 16, 17))


@pytest.mark.parametrize("anim", ANIMS)
def test_down_shows_face(anim):
    clip = load_clip(ViewKind.topdown4, anim, Direction.down)
    for k in clip.keyframes:
        assert all(k.points[i] is not None for i in (0, 14, 15, 16, 17))


def test_neutral_all_directions():
    assert all(len(load_neutral(ViewKind.topdown4, d).points) == 18 for d in Direction)


def test_list_clips_covers_every_animation_and_direction():
    assert sorted(list_clips(ViewKind.topdown4)) == sorted((a, d) for a in ANIMS for d in DIRS)


@pytest.mark.parametrize("anim", ANIMS)
@pytest.mark.parametrize("d", DIRS)
def test_character_fills_canvas(anim, d):
    clip = load_clip(ViewKind.topdown4, anim, d)
    for k in clip.keyframes:
        ys = [p[1] for p in k.points if p]
        xs = [p[0] for p in k.points if p]
        top = 0.26 if d == Direction.up else 0.2  # back view has no head keypoints, neck is highest
        assert 0.0 < min(ys) <= top and 0.8 <= max(ys) <= 0.97
        assert 0.1 < min(xs) and max(xs) < 0.9
