"""Render a Pose as an OpenPose-style skeleton image (ControlNet input)."""

import math

from PIL import Image, ImageDraw

from pixelforge.poses.model import Pose

# COCO-18 indices: 0 nose, 1 neck, 2 r_shoulder, 3 r_elbow, 4 r_wrist, 5 l_shoulder, 6 l_elbow,
# 7 l_wrist, 8 r_hip, 9 r_knee, 10 r_ankle, 11 l_hip, 12 l_knee, 13 l_ankle, 14 r_eye, 15 l_eye,
# 16 r_ear, 17 l_ear.
OPENPOSE_LIMBS: list[tuple[int, int]] = [
    (1, 2), (1, 5), (2, 3), (3, 4), (5, 6), (6, 7), (1, 8), (8, 9), (9, 10),
    (1, 11), (11, 12), (12, 13), (1, 0), (0, 14), (14, 16), (0, 15), (15, 17),
]  # fmt: skip

OPENPOSE_COLORS: list[tuple[int, int, int]] = [
    (255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0), (85, 255, 0),
    (0, 255, 0), (0, 255, 85), (0, 255, 170), (0, 255, 255), (0, 170, 255), (0, 85, 255),
    (0, 0, 255), (85, 0, 255), (170, 0, 255), (255, 0, 255), (255, 0, 170), (255, 0, 85),
]  # fmt: skip


def render_pose(pose: Pose, size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    width = max(2, size // 64)
    px = [None if p is None else (p[0] * (size - 1), p[1] * (size - 1)) for p in pose.points]

    for (i, j), color in zip(OPENPOSE_LIMBS, OPENPOSE_COLORS, strict=False):
        a, b = px[i], px[j]
        if a is None or b is None:
            continue
        # Thick limb as a rotated filled ellipse-like polygon, as in the OpenPose annotator.
        cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        angle = math.atan2(b[1] - a[1], b[0] - a[0])
        half_l, half_w = length / 2, width
        poly = []
        for k in range(24):
            th = 2 * math.pi * k / 24
            ex, ey = half_l * math.cos(th), half_w * math.sin(th)
            poly.append(
                (
                    cx + ex * math.cos(angle) - ey * math.sin(angle),
                    cy + ex * math.sin(angle) + ey * math.cos(angle),
                )
            )
        draw.polygon(poly, fill=color)

    r = width
    for p, color in zip(px, OPENPOSE_COLORS):
        if p is not None:
            draw.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=color)
    return img
