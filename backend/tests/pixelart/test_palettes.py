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


def _reference_kmeans(pixels, k, seed=0, max_iter=20):
    """The original (N, k, 3) float64 implementation, kept as an oracle."""
    data = np.asarray(pixels, dtype=np.uint8).reshape(-1, 3)
    distinct = np.unique(data, axis=0)
    if len(distinct) <= k:
        return [(int(r), int(g), int(b)) for r, g, b in distinct]
    pts = data.astype(np.float64)
    rng = np.random.default_rng(seed)
    centers = np.empty((k, 3))
    centers[0] = pts[rng.integers(len(pts))]
    closest = ((pts - centers[0]) ** 2).sum(axis=1)
    for i in range(1, k):
        total = closest.sum()
        idx = rng.choice(len(pts), p=closest / total) if total > 0 else rng.integers(len(pts))
        centers[i] = pts[idx]
        closest = np.minimum(closest, ((pts - centers[i]) ** 2).sum(axis=1))
    for _ in range(max_iter):
        dist = ((pts[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        labels = dist.argmin(axis=1)
        new = centers.copy()
        for i in range(k):
            members = pts[labels == i]
            if len(members):
                new[i] = members.mean(axis=0)
        if np.allclose(new, centers):
            centers = new
            break
        centers = new
    result = []
    for c in np.rint(centers).astype(int):
        color = (int(c[0]), int(c[1]), int(c[2]))
        if color not in result:
            result.append(color)
    return result


def test_kmeans_matches_reference_on_fixed_input():
    rng = np.random.default_rng(11)
    base = rng.integers(0, 256, size=(40, 3), dtype=np.uint8)
    px = base[rng.integers(0, len(base), size=3000)]  # many duplicated pixels
    for k in (3, 8, 16):
        assert kmeans_palette(px, k, seed=2) == _reference_kmeans(px, k, seed=2)


def test_kmeans_large_input_is_fast():
    import time

    rng = np.random.default_rng(0)
    px = rng.integers(0, 256, size=(200_000, 3), dtype=np.uint8)
    start = time.perf_counter()
    pal = kmeans_palette(px, 64, seed=0)
    assert time.perf_counter() - start < 2.0
    assert 1 <= len(pal) <= 64


def test_quantize_matches_bruteforce():
    rng = np.random.default_rng(3)
    arr = rng.integers(0, 256, size=(30, 30, 4), dtype=np.uint8)
    palette = [tuple(int(v) for v in c) for c in rng.integers(0, 256, size=(24, 3))]
    out = np.array(quantize(Image.fromarray(arr, "RGBA"), palette))
    pal = np.array(palette, dtype=np.int64)
    rgb = arr[..., :3].reshape(-1, 1, 3).astype(np.int64)
    expected = pal[((rgb - pal[None]) ** 2).sum(axis=2).argmin(axis=1)].reshape(30, 30, 3)
    assert (out[..., :3] == expected).all() and (out[..., 3] == arr[..., 3]).all()
