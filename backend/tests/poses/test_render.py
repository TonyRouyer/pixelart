from pixelforge.poses.model import Pose
from pixelforge.poses.render import OPENPOSE_COLORS, OPENPOSE_LIMBS, render_pose


def standing_pose() -> Pose:
    pts = [(0.5, 0.1), (0.5, 0.2), (0.4, 0.2), (0.35, 0.35), (0.33, 0.5), (0.6, 0.2), (0.65, 0.35),
           (0.67, 0.5), (0.45, 0.5), (0.45, 0.7), (0.45, 0.9), (0.55, 0.5), (0.55, 0.7), (0.55, 0.9),
           (0.48, 0.08), (0.52, 0.08), (0.45, 0.1), (0.55, 0.1)]  # fmt: skip
    return Pose(points=pts)


def test_render_pose_draws_on_black():
    img = render_pose(standing_pose(), 256)
    assert img.size == (256, 256) and img.mode == "RGB" and img.getpixel((0, 0)) == (0, 0, 0)
    assert img.getbbox() is not None


def test_render_skips_limbs_with_missing_endpoint():
    assert render_pose(Pose(points=[None] * 18), 128).getbbox() is None


def test_constants():
    assert len(OPENPOSE_LIMBS) == 17 and len(OPENPOSE_COLORS) == 18
