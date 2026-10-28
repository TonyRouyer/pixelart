from helpers import COLOR, colored_frames

from pixelforge.domain.models import Direction
from pixelforge.export.sheet import build_sheet


def test_sheet_dimensions_and_rows():
    sheet = build_sheet(colored_frames(per_dir=6, size=64), 64)
    assert sheet.size == (384, 256)
    assert sheet.mode == "RGBA"
    assert sheet.getpixel((10, 64 + 10)) == COLOR[Direction.left]
    assert sheet.getpixel((10, 10)) == COLOR[Direction.down]
    assert sheet.getpixel((5 * 64 + 10, 3 * 64 + 10)) == COLOR[Direction.up]


def test_sheet_padding_dimensions_and_offsets():
    sheet = build_sheet(colored_frames(per_dir=3, size=16), 16, padding=2)
    assert sheet.size == (3 * 18 - 2, 4 * 18 - 2)
    assert sheet.getpixel((18 + 1, 18 + 1)) == COLOR[Direction.left]
    assert sheet.getpixel((16, 1))[3] == 0  # gutter is transparent


def test_sheet_uneven_rows():
    frames = colored_frames(per_dir=6, size=32)
    frames[Direction.up] = frames[Direction.up][:4]
    sheet = build_sheet(frames, 32)
    assert sheet.size == (192, 128)
    assert sheet.getpixel((5 * 32 + 1, 3 * 32 + 1))[3] == 0
