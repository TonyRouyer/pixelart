"""Sprite sheet assembly: one row per direction, one column per frame."""

from __future__ import annotations

from PIL import Image

from pixelforge.domain.models import DIRECTION_ORDER, Direction

ProcessedAnimation = dict[Direction, list[Image.Image]]


def build_sheet(frames: ProcessedAnimation, size: int, padding: int = 0) -> Image.Image:
    """Row r holds DIRECTION_ORDER[r]; width follows the longest row."""
    step = size + padding
    columns = max((len(frames.get(d, [])) for d in DIRECTION_ORDER), default=0)
    width = max(columns * step - padding, 0)
    height = len(DIRECTION_ORDER) * step - padding
    sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for row, direction in enumerate(DIRECTION_ORDER):
        for col, frame in enumerate(frames.get(direction, [])):
            sheet.paste(frame.convert("RGBA"), (col * step, row * step))
    return sheet
