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


def _fill_runs(seeds: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Extend ``seeds`` to every horizontal run of ``mask`` pixels that contains one of them."""
    starts = mask.copy()
    starts[:, 1:] &= ~mask[:, :-1]
    run_ids = np.cumsum(starts.ravel()).reshape(mask.shape) * mask
    seeded = np.zeros(int(run_ids.max()) + 1, dtype=bool)
    seeded[run_ids[seeds & mask]] = True
    seeded[0] = False
    return seeded[run_ids]


def _flood_from_border(mask: np.ndarray) -> np.ndarray:
    """``mask`` pixels 4-connected to the image border through ``mask`` pixels.

    Alternating row and column run fills grow the region until it stops changing; each pass is
    vectorised, and a few passes are enough unless the background winds like a maze.
    """
    region = np.zeros_like(mask)
    region[0, :], region[-1, :] = mask[0, :], mask[-1, :]
    region[:, 0], region[:, -1] = mask[:, 0], mask[:, -1]
    while True:
        grown = _fill_runs(region, mask)
        grown = _fill_runs(grown.T, mask.T).T
        if np.array_equal(grown, region):
            return region
        region = grown


def remove_background_colorkey(img: Image.Image, tolerance: int = 32) -> Image.Image:
    """Make the background transparent by flood-filling from the frame borders.

    The background colour is the per-channel median of the border pixels. Pixels whose RGB
    Euclidean distance to it is <= tolerance and that are 4-connected to the border through such
    pixels get alpha 0; similar pixels enclosed by the character stay opaque. An image that
    already has transparency is returned unchanged (as a copy).
    """
    arr = _rgba_array(img)
    if arr.size == 0 or arr[..., 3].min() < 255:
        return Image.fromarray(arr, "RGBA")
    rgb = arr[..., :3]
    border = np.concatenate([rgb[0], rgb[-1], rgb[1:-1, 0], rgb[1:-1, -1]])
    background = np.median(border, axis=0)
    diff = rgb.astype(np.float32) - background.astype(np.float32)
    similar = (diff**2).sum(axis=-1) <= tolerance**2
    arr[_flood_from_border(similar), 3] = 0
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
