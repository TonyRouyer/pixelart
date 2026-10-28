from PIL import Image

from pixelforge.grid import cell_box, grid_shape

CELL_COLORS = [(250, 0, 0), (0, 250, 0), (0, 0, 250), (250, 250, 0), (0, 250, 250), (250, 0, 250)]


def input_of(wf: dict, param: str):
    prefix = f"IN:{param}:"
    for node in wf.values():
        title = node.get("_meta", {}).get("title", "")
        if title.startswith(prefix):
            return node["inputs"][title[len(prefix) :]]
    raise KeyError(param)


def grid_image_with_cell_colors(n: int, cell: int) -> Image.Image:
    cols, rows = grid_shape(n)
    img = Image.new("RGBA", (cols * cell, rows * cell), (0, 0, 0, 255))
    for i in range(n):
        img.paste(CELL_COLORS[i % len(CELL_COLORS)] + (255,), cell_box(i, n, cell))
    return img


def sprite(color=(10, 20, 30, 255), size=(64, 48)) -> Image.Image:
    return Image.new("RGBA", size, color)
