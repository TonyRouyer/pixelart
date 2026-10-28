import numpy as np
from PIL import Image

from pixelforge.domain.models import DIRECTION_ORDER, Direction, OutlineSettings, PixelSettings
from pixelforge.pixelart.palettes import PRESET_PALETTES
from pixelforge.pixelart.pipeline import finalize_animation, prepare_animation, process_animation


def opaque_pixels(img):
    arr = np.array(img)
    return {tuple(int(v) for v in px) for px in arr[arr[..., 3] == 255]}


BG = (220, 220, 220, 255)


def body_frame(arm=0, color=(200, 0, 0)):
    img = Image.new("RGBA", (200, 200), BG)
    img.paste((*color, 255), (80, 40, 120, 180))
    if arm:
        img.paste((*color, 255), (120, 60, 120 + arm, 80))
    return img


def fake_frames(dirs=4, n=6):
    return {d: [body_frame(i) for i in range(n)] for d in list(DIRECTION_ORDER)[:dirs]}


def frames_with_moving_arm():
    return {Direction.down: [body_frame(arm) for arm in (0, 20, 40, 10)]}


def test_process_output_shape_and_palette():
    out = process_animation(
        fake_frames(dirs=4, n=6), PixelSettings(), 64, (32, 60), [(0, 0, 0), (255, 0, 0)]
    )
    assert list(out) == list(DIRECTION_ORDER) and all(len(v) == 6 for v in out.values())
    colors = {px[:3] for f in out[Direction.down] for px in opaque_pixels(f)}
    assert colors <= {(0, 0, 0), (255, 0, 0)}


def test_output_order_follows_direction_order():
    frames = {Direction.up: [body_frame()], Direction.down: [body_frame()]}
    out = process_animation(frames, PixelSettings(), 32, (16, 30), PRESET_PALETTES["pico8"])
    assert list(out) == [Direction.down, Direction.up]


def test_process_shared_bbox_no_jitter():
    out = process_animation(
        frames_with_moving_arm(), PixelSettings(), 64, (32, 60), PRESET_PALETTES["pico8"]
    )
    assert len({f.getbbox()[3] for f in out[Direction.down]}) == 1


def test_process_animation_with_empty_frame():
    out = process_animation(
        {Direction.down: [Image.new("RGBA", (200, 200))]},
        PixelSettings(),
        32,
        (16, 30),
        [(0, 0, 0), (9, 9, 9)],
    )
    assert out[Direction.down][0].size == (32, 32)
    assert out[Direction.down][0].getbbox() is None


def test_prepare_then_finalize_equals_process():
    frames = fake_frames(dirs=2, n=3)
    pal = [(0, 0, 0), (255, 0, 0)]
    settings = PixelSettings()
    prepared = prepare_animation(frames, settings, 48, (24, 44))
    assert all(f.size == (48, 48) for fs in prepared.values() for f in fs)
    a = finalize_animation(prepared, settings, pal)
    b = process_animation(frames, settings, 48, (24, 44), pal)
    assert all(x.tobytes() == y.tobytes() for d in a for x, y in zip(a[d], b[d], strict=True))


def test_outline_color_not_quantized():
    settings = PixelSettings(outline=OutlineSettings(enabled=True, color="#123456"))
    out = process_animation(
        fake_frames(dirs=1, n=2), settings, 64, (32, 60), [(0, 0, 0), (255, 0, 0)]
    )
    colors = {px[:3] for px in opaque_pixels(out[Direction.down][0])}
    assert (0x12, 0x34, 0x56) in colors
