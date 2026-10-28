"""Full pixel-art pipeline: raw AI frames -> clean, palette-bound cells."""

from __future__ import annotations

from PIL import Image

from pixelforge.domain.models import DIRECTION_ORDER, Direction, PixelSettings
from pixelforge.pixelart.palettes import RGB, quantize
from pixelforge.pixelart.steps import (
    add_outline,
    common_bbox,
    fit_to_cell,
    remove_background_colorkey,
    threshold_alpha,
)

Frames = dict[Direction, list[Image.Image]]


def _ordered(frames: Frames) -> list[Direction]:
    return [d for d in DIRECTION_ORDER if d in frames]


def prepare_animation(
    frames: Frames, settings: PixelSettings, size: int, anchor: tuple[int, int]
) -> Frames:
    """Colorkey, shared bbox over all directions, fit to cell, binarise alpha."""
    keyed = {d: [remove_background_colorkey(f) for f in frames[d]] for d in _ordered(frames)}
    bbox = common_bbox([f for fs in keyed.values() for f in fs])
    if bbox is None:
        return {d: [Image.new("RGBA", (size, size)) for _ in fs] for d, fs in keyed.items()}
    return {
        d: [
            threshold_alpha(fit_to_cell(f, bbox, size, anchor), settings.alpha_threshold)
            for f in fs
        ]
        for d, fs in keyed.items()
    }


def finalize_animation(prepared: Frames, settings: PixelSettings, palette: list[RGB]) -> Frames:
    """Quantize to the palette, then outline (the outline colour is not quantized)."""
    outline = settings.outline
    color: RGB | None = None
    if outline.enabled:
        c = outline.color
        color = (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))
    out: Frames = {}
    for d in _ordered(prepared):
        cells = [quantize(f, palette) for f in prepared[d]]
        out[d] = [add_outline(f, color) for f in cells] if color else cells
    return out


def process_animation(
    frames: Frames,
    settings: PixelSettings,
    size: int,
    anchor: tuple[int, int],
    palette: list[RGB],
) -> Frames:
    return finalize_animation(prepare_animation(frames, settings, size, anchor), settings, palette)
