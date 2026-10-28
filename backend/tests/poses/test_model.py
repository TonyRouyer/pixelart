import pytest
from pydantic import ValidationError

from pixelforge.poses.model import Keyframe, Pose, PoseClip, sample


def pts(x: float | None) -> list[tuple[float, float] | None]:
    return [None if x is None else (x, 0.5)] + [(0.5, 0.5)] * 17


def kf(t: float, x: float | None) -> Keyframe:
    return Keyframe(t=t, points=pts(x))


def test_sample_loop_excludes_endpoint():
    clip = PoseClip(loop=True, keyframes=[kf(0.0, x=0.0), kf(0.5, x=1.0)])
    xs = [p.points[0][0] for p in sample(clip, 4)]
    assert xs == pytest.approx([0.0, 0.5, 1.0, 0.5])


def test_sample_no_loop_includes_endpoint():
    clip = PoseClip(loop=False, keyframes=[kf(0.0, x=0.0), kf(1.0, x=1.0)])
    assert [p.points[0][0] for p in sample(clip, 3)] == pytest.approx([0.0, 0.5, 1.0])


def test_sample_missing_point_stays_missing():
    clip = PoseClip(loop=False, keyframes=[kf(0.0, x=0.0), kf(1.0, x=None)])
    assert sample(clip, 3)[1].points[0] is None


def test_sample_single_frame_no_loop():
    clip = PoseClip(loop=False, keyframes=[kf(0.0, x=0.2), kf(1.0, x=1.0)])
    assert [p.points[0][0] for p in sample(clip, 1)] == pytest.approx([0.2])


def test_pose_requires_18_points():
    with pytest.raises(ValidationError):
        Pose(points=[(0.5, 0.5)] * 17)


def test_pose_rejects_out_of_range():
    with pytest.raises(ValidationError):
        Pose(points=[(1.5, 0.5)] + [None] * 17)


def test_clip_first_t_must_be_zero():
    with pytest.raises(ValidationError):
        PoseClip(loop=False, keyframes=[kf(0.2, 0.0), kf(1.0, 1.0)])


def test_clip_keyframes_must_be_sorted():
    with pytest.raises(ValidationError):
        PoseClip(loop=False, keyframes=[kf(0.0, 0.0), kf(0.8, 1.0), kf(0.4, 1.0)])
