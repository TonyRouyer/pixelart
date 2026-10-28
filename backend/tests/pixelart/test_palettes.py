import numpy as np
import pytest
from PIL import Image

from pixelforge.domain.models import OutlineSettings, PaletteSettings, PixelSettings
from pixelforge.pixelart.palettes import (
    PRESET_PALETTES,
    character_palette,
    kmeans_palette,
    parse_palette,
    quantize,
)


def two_color_pixels(a, b, n=50):
    return np.array([a] * n + [b] * n, dtype=np.uint8)


def test_presets_sizes():
    assert len(PRESET_PALETTES["pico8"]) == 16 and len(PRESET_PALETTES["db32"]) == 32
    assert len(PRESET_PALETTES["endesga32"]) == 32
    for pal in PRESET_PALETTES.values():
        assert len(set(pal)) == len(pal)


def test_presets_known_entries():
    assert PRESET_PALETTES["pico8"][0] == (0, 0, 0)
    assert PRESET_PALETTES["pico8"][7] == (255, 241, 232)
    assert PRESET_PALETTES["db32"][0] == (0, 0, 0)
    assert PRESET_PALETTES["db32"][1] == (34, 32, 52)
    assert PRESET_PALETTES["endesga32"][0] == (190, 74, 47)


def test_parse_hex_and_gpl():
    assert parse_palette("ff0000\n#00ff00\n") == [(255, 0, 0), (0, 255, 0)]
    assert parse_palette("GIMP Palette\nName: x\n#\n255 0 0 red\n0 0 255 blue\n") == [
        (255, 0, 0),
        (0, 0, 255),
    ]


def test_parse_too_few_colors():
    with pytest.raises(ValueError):
        parse_palette("ff0000\n")


def test_kmeans_finds_two_clusters():
    pal = kmeans_palette(two_color_pixels((250, 0, 0), (0, 0, 250)), 2)
    assert sorted(pal) == [(0, 0, 250), (250, 0, 0)]
    assert all(isinstance(c, int) for col in pal for c in col)


def test_kmeans_fewer_distinct_than_k():
    pal = kmeans_palette(two_color_pixels((1, 2, 3), (4, 5, 6)), 8)
    assert sorted(pal) == [(1, 2, 3), (4, 5, 6)]


def test_kmeans_deterministic():
    rng = np.random.default_rng(5)
    px = rng.integers(0, 256, size=(500, 3), dtype=np.uint8)
    assert kmeans_palette(px, 6, seed=1) == kmeans_palette(px, 6, seed=1)


def test_quantize_nearest_keeps_alpha():
    img = Image.new("RGBA", (2, 1))
    img.putpixel((0, 0), (250, 10, 10, 255))
    img.putpixel((1, 0), (9, 9, 9, 0))
    out = quantize(img, [(0, 0, 0), (255, 0, 0)])
    assert out.getpixel((0, 0)) == (255, 0, 0, 255)
    assert out.getpixel((1, 0))[3] == 0


def test_character_palette_modes():
    img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    img.paste((250, 0, 0, 255), (0, 0, 5, 10))
    img.paste((0, 0, 250, 255), (5, 0, 8, 10))
    auto = PixelSettings(palette=PaletteSettings(mode="auto", colors=2))
    assert sorted(character_palette([img], auto)) == [(0, 0, 250), (250, 0, 0)]
    preset = PixelSettings(palette=PaletteSettings(mode="preset", preset="pico8"))
    assert character_palette([img], preset) == PRESET_PALETTES["pico8"]
    custom = PixelSettings(
        palette=PaletteSettings(mode="custom", custom_colors=["#ff0000", "#00ff00"])
    )
    assert character_palette([img], custom) == [(255, 0, 0), (0, 255, 0)]
    bad = PixelSettings(palette=PaletteSettings(mode="preset", preset="nope"))
    with pytest.raises(ValueError, match="unknown_palette"):
        character_palette([img], bad)


def test_character_palette_all_transparent():
    img = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    assert character_palette([img], PixelSettings()) == []


def test_outline_setting_unused_here():
    assert OutlineSettings().enabled is False
