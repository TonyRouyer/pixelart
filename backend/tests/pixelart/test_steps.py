import numpy as np
from PIL import Image

from pixelforge.pixelart.steps import (
    add_outline,
    common_bbox,
    fit_to_cell,
    remove_background_colorkey,
    threshold_alpha,
)


def solid(size, color):
    return Image.new("RGBA", size, (*color, 255))


def draw_rect(img, box, color):
    x0, y0, x1, y1 = box
    img.paste((*color, 255), (x0, y0, x1, y1))


def rect_frame(box, canvas=(50, 50), color=(200, 0, 0)):
    img = Image.new("RGBA", canvas, (0, 0, 0, 0))
    draw_rect(img, box, color)
    return img


def single_pixel_image(xy, size=11, color=(255, 0, 0)):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.putpixel(xy, (*color, 255))
    return img


def test_colorkey_removes_flat_background():
    img = solid((100, 100), (255, 255, 255))
    draw_rect(img, (40, 40, 60, 60), (200, 0, 0))
    out = remove_background_colorkey(img)
    assert out.getpixel((0, 0))[3] == 0 and out.getpixel((50, 50))[3] == 255


def test_colorkey_keeps_existing_alpha():
    img = rect_frame((10, 10, 20, 20))
    out = remove_background_colorkey(img)
    assert out.tobytes() == img.tobytes()


def test_colorkey_tolerance_and_input_untouched():
    img = solid((20, 20), (240, 240, 240))
    img.putpixel((10, 10), (230, 240, 250))  # within the default tolerance
    img.putpixel((11, 11), (100, 100, 100))
    before = img.tobytes()
    out = remove_background_colorkey(img)
    assert out.getpixel((10, 10))[3] == 0 and out.getpixel((11, 11))[3] == 255
    assert img.tobytes() == before


def test_colorkey_accepts_other_modes():
    out = remove_background_colorkey(Image.new("RGB", (10, 10), (250, 250, 250)))
    assert out.mode == "RGBA" and out.getchannel("A").getextrema() == (0, 0)


def gradient_frame(size=340, top=200, bottom=225):
    """Vertical gray gradient ``top`` -> ``bottom``, fully opaque."""
    column = np.linspace(top, bottom, size).round().astype(np.uint8)
    arr = np.empty((size, size, 4), dtype=np.uint8)
    arr[..., :3] = column[:, None, None]
    arr[..., 3] = 255
    return Image.fromarray(arr, "RGBA")


def character_with_enclosed_patch(size=340):
    """Gradient background, a dark character whose middle holds a background-gray patch."""
    img = gradient_frame(size)
    draw_rect(img, (100, 80, 240, 300), (40, 30, 90))
    draw_rect(img, (140, 140, 200, 200), (212, 212, 212))  # same gray as the background
    return img


def test_colorkey_removes_gradient_background():
    img = gradient_frame()
    draw_rect(img, (150, 150, 190, 190), (200, 0, 0))
    alpha = np.array(remove_background_colorkey(img))[..., 3]
    character = np.zeros_like(alpha, dtype=bool)
    character[150:190, 150:190] = True
    assert (alpha[~character] == 0).all() and (alpha[character] == 255).all()


def test_colorkey_keeps_enclosed_background_colour():
    alpha = np.array(remove_background_colorkey(character_with_enclosed_patch()))[..., 3]
    assert (alpha[80:300, 100:240] == 255).all()  # the gray patch inside stays opaque
    assert alpha[:80].max() == 0 and alpha[300:].max() == 0
    assert alpha[:, :100].max() == 0 and alpha[:, 240:].max() == 0


def test_colorkey_tolerance_is_euclidean_rgb():
    img = solid((20, 20), (240, 240, 240))
    img.putpixel((0, 10), (210, 240, 240))  # distance 30: background
    img.putpixel((10, 0), (220, 220, 220))  # distance 34.6 (20 per channel): kept
    alpha = remove_background_colorkey(img).getchannel("A")
    assert alpha.getpixel((0, 10)) == 0 and alpha.getpixel((10, 0)) == 255


def test_colorkey_is_fast_on_large_frames():
    import time

    img = character_with_enclosed_patch()
    best = float("inf")
    for _ in range(5):
        start = time.perf_counter()
        remove_background_colorkey(img)
        best = min(best, time.perf_counter() - start)
    assert best < 0.05


def test_common_bbox_union():
    frames = [rect_frame((10, 10, 20, 20)), rect_frame((30, 5, 40, 15))]
    assert common_bbox(frames) == (10, 5, 40, 20)


def test_common_bbox_all_empty():
    assert common_bbox([Image.new("RGBA", (50, 50))]) is None
    assert common_bbox([]) is None


def test_common_bbox_alpha_min():
    img = rect_frame((10, 10, 20, 20))
    img.putpixel((40, 40), (0, 0, 0, 5))
    assert common_bbox([img], alpha_min=1) == (10, 10, 41, 41)
    assert common_bbox([img], alpha_min=10) == (10, 10, 20, 20)


def test_fit_to_cell_anchors_feet():
    out = fit_to_cell(rect_frame((10, 0, 30, 80), canvas=(100, 100)), (10, 0, 30, 80), 64, (32, 60))
    assert out.size == (64, 64)
    bb = out.getbbox()
    assert bb[3] == 60 and abs((bb[0] + bb[2]) / 2 - 32) <= 1


def test_fit_to_cell_same_bbox_same_scale():
    bbox = (10, 0, 30, 80)
    a = fit_to_cell(rect_frame((10, 0, 30, 80), canvas=(100, 100)), bbox, 64, (32, 60))
    b = fit_to_cell(rect_frame((10, 40, 30, 80), canvas=(100, 100)), bbox, 64, (32, 60))
    assert a.getbbox()[3] == b.getbbox()[3] == 60
    assert a.getbbox()[0] == b.getbbox()[0] and a.getbbox()[2] == b.getbbox()[2]
    assert b.getbbox()[1] > a.getbbox()[1]


def test_fit_to_cell_wide_bbox_limited_by_width():
    out = fit_to_cell(rect_frame((0, 0, 100, 10), canvas=(100, 100)), (0, 0, 100, 10), 32, (16, 30))
    bb = out.getbbox()
    assert out.size == (32, 32) and bb[2] - bb[0] <= 30 and bb[3] == 30


def test_fit_to_cell_does_not_mutate_input():
    img = rect_frame((10, 0, 30, 80), canvas=(100, 100))
    before = img.tobytes()
    fit_to_cell(img, (10, 0, 30, 80), 64, (32, 60))
    assert img.tobytes() == before


def test_threshold_alpha_binary():
    img = Image.new("RGBA", (4, 1))
    for x, a in enumerate([0, 99, 100, 255]):
        img.putpixel((x, 0), (10, 20, 30, a))
    out = threshold_alpha(img, 100)
    assert list(np.array(out)[0, :, 3]) == [0, 0, 255, 255]
    assert img.getpixel((1, 0))[3] == 99


def test_outline_only_on_transparent_neighbours():
    out = add_outline(single_pixel_image((5, 5), size=11), (0, 0, 0))
    assert out.getpixel((5, 4)) == (0, 0, 0, 255) and out.getpixel((4, 4))[3] == 0
    assert out.getpixel((5, 5)) == (255, 0, 0, 255)
    assert int((np.array(out)[..., 3] > 0).sum()) == 5


def test_outline_at_image_border():
    out = add_outline(single_pixel_image((0, 0), size=3), (0, 0, 0))
    assert out.getpixel((1, 0))[3] == 255 and out.getpixel((0, 1))[3] == 255
