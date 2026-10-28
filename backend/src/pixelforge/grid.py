"""Compose and split square-cell image grids (row-major order)."""

from math import ceil, sqrt

from PIL import Image


def grid_shape(n: int) -> tuple[int, int]:
    """Return (cols, rows) for n cells."""
    cols = ceil(sqrt(n))
    rows = ceil(n / cols)
    return cols, rows


def cell_size(n: int, canvas: int) -> int:
    """Largest cell size, a multiple of 8, fitting n cells in a canvas-sized square."""
    cols, rows = grid_shape(n)
    return canvas // max(cols, rows) // 8 * 8


def cell_box(index: int, n: int, cell: int) -> tuple[int, int, int, int]:
    cols, _ = grid_shape(n)
    x, y = (index % cols) * cell, (index // cols) * cell
    return x, y, x + cell, y + cell


def compose_grid(
    images: list[Image.Image], cell: int, background: tuple[int, int, int] = (0, 0, 0)
) -> Image.Image:
    n = len(images)
    cols, rows = grid_shape(n)
    canvas = Image.new("RGB", (cols * cell, rows * cell), background)
    for i, img in enumerate(images):
        scale = min(cell / img.width, cell / img.height)
        w = max(1, round(img.width * scale))
        h = max(1, round(img.height * scale))
        resized = img.convert("RGB").resize((w, h), Image.Resampling.LANCZOS)
        x0, y0, _, _ = cell_box(i, n, cell)
        canvas.paste(resized, (x0 + (cell - w) // 2, y0 + (cell - h) // 2))
    return canvas


def split_grid(image: Image.Image, n: int) -> list[Image.Image]:
    cols, _ = grid_shape(n)
    cell = image.width // cols
    return [image.crop(cell_box(i, n, cell)) for i in range(n)]
