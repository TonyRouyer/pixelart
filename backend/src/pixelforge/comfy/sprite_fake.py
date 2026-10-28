"""ComfyUI stand-in that answers every bundled workflow with plausible sprite images.

Each "character" is a coloured rectangle centred on the flat ``BACKGROUND_RGB`` gray, at the size
the workflow asks for. Used by the service tests and by the GPU-less demo mode.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from pixelforge.comfy.fake import FakeComfyClient
from pixelforge.generation.base import BACKGROUND_RGB
from pixelforge.grid import cell_box, grid_shape

SPRITE_COLORS: tuple[tuple[int, int, int], ...] = (
    (200, 40, 40),
    (40, 90, 200),
    (230, 180, 40),
    (60, 160, 70),
    (150, 60, 170),
    (230, 120, 40),
)
_MAX_CELLS = 64
_KEY_TOLERANCE = 24

UploadsGetter = Callable[[], dict[str, Image.Image]]


def _inputs(workflow: dict) -> dict[str, Any]:
    """Bound values of a workflow, by parameter name (from ``IN:<param>:<field>`` titles)."""
    out: dict[str, Any] = {}
    for node in workflow.values():
        title = node.get("_meta", {}).get("title", "")
        if title.startswith("IN:"):
            param, _, field = title[3:].partition(":")
            out[param] = node["inputs"][field]
    return out


def _draw_sprite(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], index: int) -> None:
    """A rectangle centred in ``box``: 40 % of its width, 60 % of its height."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    rw, rh = max(1, w * 2 // 5), max(1, h * 3 // 5)
    left, top = x0 + (w - rw) // 2, y0 + (h - rh) // 2
    draw.rectangle(
        (left, top, left + rw - 1, top + rh - 1), fill=SPRITE_COLORS[index % len(SPRITE_COLORS)]
    )


def _sprite(size: tuple[int, int], index: int) -> Image.Image:
    img = Image.new("RGB", size, BACKGROUND_RGB)
    _draw_sprite(ImageDraw.Draw(img), (0, 0, *size), index)
    return img


def _layouts(width: int, height: int) -> list[tuple[int, int, int]]:
    """Grid layouts (cols, rows, cell) of ``grid_shape`` that tile width x height, finest first."""
    found: list[tuple[int, int, int]] = []
    for n in range(1, _MAX_CELLS + 1):
        cols, rows = grid_shape(n)
        if width % cols or height % rows or width // cols != height // rows:
            continue
        layout = (cols, rows, width // cols)
        if layout not in found:
            found.append(layout)
    return sorted(found, key=lambda lay: lay[0] * lay[1], reverse=True)


def _touches_cell_edges(mask: np.ndarray, cols: int, rows: int, cell: int) -> bool:
    lines_x = sorted({x for k in range(cols + 1) for x in (k * cell - 1, k * cell)})
    lines_y = sorted({y for k in range(rows + 1) for y in (k * cell - 1, k * cell)})
    xs = [x for x in lines_x if 0 <= x < mask.shape[1]]
    ys = [y for y in lines_y if 0 <= y < mask.shape[0]]
    return bool(mask[:, xs].any() or mask[ys, :].any())


def _grid_cells(width: int, height: int, pose: Image.Image | None) -> list[tuple[int, ...]]:
    """Boxes of the cells holding a pose.

    The cell count is not part of the workflow, so the layout is read from the pose grid: the
    finest layout whose cell borders no skeleton crosses (poses are drawn with a margin).
    """
    layouts = _layouts(width, height)
    if not layouts:
        return [(0, 0, width, height)]
    mask = None
    if pose is not None and pose.size == (width, height):
        mask = np.asarray(pose.convert("L")) > 0
    chosen = layouts[-1]
    if mask is not None:
        for layout in layouts:
            if not _touches_cell_edges(mask, *layout):
                chosen = layout
                break
    cols, rows, cell = chosen
    n = cols * rows
    boxes = [cell_box(i, n, cell) for i in range(n)]
    if mask is None:
        return boxes
    return [b for b in boxes if mask[b[1] : b[3], b[0] : b[2]].any()] or boxes


def _key_out_background(img: Image.Image) -> Image.Image:
    arr = np.array(img.convert("RGBA"), dtype=np.uint8)
    diff = arr[..., :3].astype(np.int32) - np.array(BACKGROUND_RGB, dtype=np.int32)
    arr[(np.abs(diff) <= _KEY_TOLERANCE).all(axis=-1), 3] = 0
    return Image.fromarray(arr)


def make_sprite_responder(uploads: UploadsGetter) -> Callable[[dict], list[Image.Image]]:
    """Responder for ``FakeComfyClient``; ``uploads`` returns the images uploaded so far."""

    def respond(workflow: dict) -> list[Image.Image]:
        values = _inputs(workflow)
        images = uploads()
        if "mask_image" in values:  # pose_inpaint: redraw the masked cell of the source grid
            source = images[values["source_image"]].convert("RGB")
            box = images[values["mask_image"]].convert("L").getbbox() or (0, 0, *source.size)
            draw = ImageDraw.Draw(source)
            draw.rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill=BACKGROUND_RGB)
            _draw_sprite(draw, box, 3)
            return [source]
        if "source_image" in values:  # remove_bg
            return [_key_out_background(images[values["source_image"]])]
        size = (int(values["width"]), int(values["height"]))
        if "pose_image" in values:  # turnaround / pose_grid
            grid = Image.new("RGB", size, BACKGROUND_RGB)
            draw = ImageDraw.Draw(grid)
            for i, box in enumerate(_grid_cells(*size, images.get(values["pose_image"]))):
                _draw_sprite(draw, box, i)
            return [grid]
        return [_sprite(size, i) for i in range(int(values["batch"]))]  # txt2img

    return respond


class SpriteFakeComfyClient(FakeComfyClient):
    """``FakeComfyClient`` answering with sprite rectangles (see ``make_sprite_responder``)."""

    def __init__(
        self, object_info: dict | None = None, models: dict[str, list[str]] | None = None
    ) -> None:
        super().__init__(make_sprite_responder(lambda: self.uploads), object_info, models)
