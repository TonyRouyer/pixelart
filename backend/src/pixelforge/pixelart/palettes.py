"""Palettes: presets, parsing, k-means extraction and nearest-colour quantization."""

from __future__ import annotations

import numpy as np
from PIL import Image

from pixelforge.domain.models import PixelSettings

RGB = tuple[int, int, int]

_MAX_SAMPLE = 200_000


def _from_hex(values: str) -> list[RGB]:
    return [(int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)) for v in values.split()]


PRESET_PALETTES: dict[str, list[RGB]] = {
    "pico8": _from_hex(
        "000000 1d2b53 7e2553 008751 ab5236 5f574f c2c3c7 fff1e8 "
        "ff004d ffa300 ffec27 00e436 29adff 83769c ff77a8 ffccaa"
    ),
    "db32": _from_hex(
        "000000 222034 45283c 663931 8f563b df7126 d9a066 eec39a "
        "fbf236 99e550 6abe30 37946e 4b692f 524b24 323c39 3f3f74 "
        "306082 5b6ee1 639bff 5fcde4 cbdbfc ffffff 9badb7 847e87 "
        "696a6a 595652 76428a ac3232 d95763 d77bba 8f974a 8a6f30"
    ),
    "endesga32": _from_hex(
        "be4a2f d77643 ead4aa e4a672 b86f50 733e39 3e2731 a22633 "
        "e43b44 f77622 feae34 fee761 63c74d 3e8948 265c42 193c3e "
        "124e89 0099db 2ce8f5 ffffff c0cbdc 8b9bb4 5a6988 3a4466 "
        "262b44 181425 ff0044 68386c b55088 f6757a e8b796 c28569"
    ),
}


def parse_palette(text: str) -> list[RGB]:
    """Parse a `.hex` (one colour per line, `#` optional) or GIMP `.gpl` palette."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    is_gpl = bool(lines) and lines[0].startswith("GIMP Palette")
    colors: list[RGB] = []
    for line in lines:
        try:
            if is_gpl:
                if line.startswith("#") or line.split(":")[0] in (
                    "GIMP Palette",
                    "Name",
                    "Columns",
                ):
                    continue
                r, g, b = (int(p) for p in line.split()[:3])
                if not all(0 <= c <= 255 for c in (r, g, b)):
                    raise ValueError
                colors.append((r, g, b))
            else:
                value = line.lstrip("#")
                if len(value) != 6:
                    raise ValueError
                colors.extend(_from_hex(value))
        except ValueError:
            raise ValueError(f"invalid palette line: {line!r}") from None
    if len(colors) < 2:
        raise ValueError("palette needs at least 2 colors")
    return colors


def _augmented(points: np.ndarray) -> np.ndarray:
    """(N, 4) float32 rows [r, g, b, 1] for `_nearest`."""
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 3)
    return np.hstack([pts, np.ones((len(pts), 1), dtype=np.float32)])


def _nearest(augmented: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Index of the nearest centre for each row of `_augmented` points.

    |x - c|^2 = |x|^2 - 2 x.c + |c|^2; |x|^2 does not change the argmin, so one (N, 4) x (4, k)
    float32 product gives the ranking without any (N, k, 3) intermediate.
    """
    c = np.asarray(centers, dtype=np.float32)
    weights = np.hstack([-2.0 * c, (c * c).sum(axis=1, keepdims=True)])
    return (augmented @ weights.T).argmin(axis=1)


def _unique_colors(data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Distinct (N, 3) uint8 colours, sorted like ``np.unique(axis=0)``, and their counts."""
    packed = (data[:, 0].astype(np.uint32) << 16) | (data[:, 1].astype(np.uint32) << 8) | data[:, 2]
    keys, counts = np.unique(packed, return_counts=True)
    distinct = np.stack([keys >> 16, keys >> 8, keys], axis=1) & 255
    return distinct.astype(np.uint8), counts


def kmeans_palette(pixels: np.ndarray, k: int, seed: int = 0, max_iter: int = 20) -> list[RGB]:
    """Deterministic k-means (k-means++ init) over (N, 3) RGB pixels.

    The seeding samples the pixels themselves (duplicates included); the Lloyd iterations then
    run on the distinct colours weighted by their pixel counts, which gives the same centroids.
    """
    data = np.asarray(pixels, dtype=np.uint8).reshape(-1, 3)
    distinct, counts = _unique_colors(data)
    if len(distinct) <= k:
        return [(int(r), int(g), int(b)) for r, g, b in distinct]
    pts = data.astype(np.float64)
    channels = [np.ascontiguousarray(pts[:, ch]) for ch in range(3)]

    def sq_dist(center: np.ndarray) -> np.ndarray:
        r, g, b = ((col - v) ** 2 for col, v in zip(channels, center, strict=True))
        return r + g + b

    rng = np.random.default_rng(seed)
    centers = np.empty((k, 3))
    centers[0] = pts[rng.integers(len(pts))]
    closest = sq_dist(centers[0])
    for i in range(1, k):
        total = closest.sum()
        idx = rng.choice(len(pts), p=closest / total) if total > 0 else rng.integers(len(pts))
        centers[i] = pts[idx]
        np.minimum(closest, sq_dist(centers[i]), out=closest)
    colors = distinct.astype(np.float64)
    weights = counts.astype(np.float64)
    augmented = _augmented(distinct)
    for _ in range(max_iter):
        labels = _nearest(augmented, centers)
        mass = np.bincount(labels, weights=weights, minlength=k)
        sums = np.stack(
            [np.bincount(labels, weights=weights * colors[:, ch], minlength=k) for ch in range(3)],
            axis=1,
        )
        new = centers.copy()
        filled = mass > 0
        new[filled] = sums[filled] / mass[filled, None]
        if np.allclose(new, centers):
            centers = new
            break
        centers = new
    result: list[RGB] = []
    for c in np.rint(centers).astype(int):
        color = (int(c[0]), int(c[1]), int(c[2]))
        if color not in result:
            result.append(color)
    return result


def quantize(img: Image.Image, palette: list[RGB]) -> Image.Image:
    """Map every pixel to the nearest palette colour (RGB distance); alpha kept, no dithering."""
    arr = np.array(img.convert("RGBA"), dtype=np.uint8)
    if not palette:
        return Image.fromarray(arr)
    pal = np.array(palette, dtype=np.uint8)
    nearest = _nearest(_augmented(arr[..., :3]), pal)
    arr[..., :3] = pal[nearest].reshape(arr.shape[0], arr.shape[1], 3)
    return Image.fromarray(arr)


def character_palette(frames: list[Image.Image], settings: PixelSettings) -> list[RGB]:
    """Palette for a character. `frames` must be prepared frames (background removed, downscaled).

    auto: k-means over the opaque pixels of all frames; preset/custom: the configured palette.
    """
    cfg = settings.palette
    if cfg.mode == "preset":
        if cfg.preset not in PRESET_PALETTES:
            raise ValueError("unknown_palette")
        return list(PRESET_PALETTES[cfg.preset])
    if cfg.mode == "custom":
        return [
            (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)) for c in (cfg.custom_colors or [])
        ]
    chunks = []
    for frame in frames:
        arr = np.array(frame.convert("RGBA"), dtype=np.uint8)
        chunks.append(arr[arr[..., 3] > 0][:, :3])
    pixels = np.concatenate(chunks) if chunks else np.empty((0, 3), dtype=np.uint8)
    if len(pixels) == 0:
        return []
    if len(pixels) > _MAX_SAMPLE:
        rng = np.random.default_rng(0)
        pixels = pixels[rng.choice(len(pixels), _MAX_SAMPLE, replace=False)]
    return kmeans_palette(pixels, cfg.colors, seed=0)
