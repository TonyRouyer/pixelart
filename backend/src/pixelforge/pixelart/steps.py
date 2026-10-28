"""Unit steps of the pixel-art pipeline.

All functions are pure: they accept any Pillow mode, convert to RGBA and return a new image.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

BBox = tuple[int, int, int, int]


def _rgba_array(img: Image.Image) -> np.ndarray:
    """Return a fresh, writable (H, W, 4) uint8 array of the image converted to RGBA."""
    return np.array(img.convert("RGBA"), dtype=np.uint8)


def remove_background_colorkey(img: Image.Image, tolerance: int = 24) -> Image.Image:
    """Make the flat background transparent.

    The background colour is the per-channel median of the four corners; pixels whose RGB
    distance to it is <= tolerance get alpha 0. An image that already has transparency is
    returned unchanged (as a copy).
    """
    arr = _rgba_array(img)
    if arr.size == 0 or arr[..., 3].min() < 255:
        return Image.fromarray(arr, "RGBA")
    corners = np.stack([arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]])[:, :3]
    background = np.median(corners, axis=0)
    diff = arr[..., :3].astype(np.float64) - background
    distance = np.sqrt((diff**2).sum(axis=-1))
    arr[distance <= tolerance, 3] = 0
    return Image.fromarray(arr, "RGBA")


def common_bbox(frames: list[Image.Image], alpha_min: int = 1) -> BBox | None:
    """Union of the opaque bounding boxes (x0, y0, x1, y1; x1/y1 exclusive), None if all empty."""
    union: BBox | None = None
    for frame in frames:
        alpha = _rgba_array(frame)[..., 3]
        ys, xs = np.nonzero(alpha >= alpha_min)
        if xs.size == 0:
            continue
        box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        if union is None:
            union = box
        else:
            union = (
                min(union[0], box[0]),
                min(union[1], box[1]),
                max(union[2], box[2]),
                max(union[3], box[3]),
            )
    return union


def fit_to_cell(frame: Image.Image, bbox: BBox, size: int, anchor: tuple[int, int]) -> Image.Image:
    """Crop to bbox, scale to fit the cell and place the bbox bottom-centre on anchor.

    Scale is min((size - 2) / bw, anchor_y / bh), identical for every frame sharing a bbox.
    Anything falling outside the size x size cell is clipped.
    """
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    anchor_x, anchor_y = anchor
    x0, y0, x1, y1 = bbox
    bw, bh = x1 - x0, y1 - y0
    if bw <= 0 or bh <= 0 or anchor_y <= 0 or size <= 2:
        return out
    scale = min((size - 2) / bw, anchor_y / bh)
    new_w = max(1, round(bw * scale))
    new_h = max(1, round(bh * scale))
    cropped = frame.convert("RGBA").crop(bbox)
    scaled = cropped.resize((new_w, new_h), Image.BOX)
    out.paste(scaled, (round(anchor_x - new_w / 2), anchor_y - new_h))
    return out


def threshold_alpha(img: Image.Image, threshold: int) -> Image.Image:
    """Binarise alpha: >= threshold becomes 255, otherwise 0."""
    arr = _rgba_array(img)
    arr[..., 3] = np.where(arr[..., 3] >= threshold, 255, 0)
    return Image.fromarray(arr, "RGBA")


def add_outline(img: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """Outline opaque pixels: transparent 4-neighbours of an opaque pixel get `color` (alpha 255)."""
    arr = _rgba_array(img)
    opaque = arr[..., 3] > 0
    neighbour = np.zeros_like(opaque)
    neighbour[1:, :] |= opaque[:-1, :]
    neighbour[:-1, :] |= opaque[1:, :]
    neighbour[:, 1:] |= opaque[:, :-1]
    neighbour[:, :-1] |= opaque[:, 1:]
    arr[neighbour & ~opaque] = (*color, 255)
    return Image.fromarray(arr, "RGBA")
