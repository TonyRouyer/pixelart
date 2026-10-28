import io

import pytest
from PIL import Image

from pixelforge.services.images import MAX_UPLOAD_BYTES, normalize_upload


def _encode(img: Image.Image, fmt: str, **kw) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt, **kw)
    return buf.getvalue()


def jpeg_bytes(size: tuple[int, int]) -> bytes:
    return _encode(Image.new("RGB", size, (200, 30, 30)), "JPEG")


def png_bytes(mode: str) -> bytes:
    if mode == "P":
        img = Image.new("RGB", (40, 30), (0, 128, 255)).convert("P")
    else:
        img = Image.new(mode, (30, 40))
    return _encode(img, "PNG")


def png_with_alpha() -> bytes:
    img = Image.new("RGBA", (50, 20), (0, 0, 0, 0))
    img.paste((10, 200, 10, 255), (10, 5, 40, 15))
    return _encode(img, "PNG")


def test_upload_normalizes_odd_images():
    for data in [
        jpeg_bytes((3000, 1200)),
        png_bytes(mode="P"),
        png_bytes(mode="LA"),
        png_with_alpha(),
    ]:
        img = normalize_upload(data)
        assert img.mode == "RGBA" and img.size[0] == img.size[1] <= 1024
    with pytest.raises(ValueError, match="unsupported_image"):
        normalize_upload(b"not an image")


def test_large_image_is_downscaled_and_centred_on_transparent_square():
    img = normalize_upload(jpeg_bytes((3000, 1200)))
    assert img.size == (1024, 1024)
    assert img.getpixel((512, 0))[3] == 0  # padding above
    assert img.getpixel((512, 512))[:3] != (0, 0, 0) and img.getpixel((512, 512))[3] == 255


def test_small_image_keeps_its_size_and_alpha():
    img = normalize_upload(png_with_alpha())
    assert img.size == (50, 50)
    assert img.getpixel((0, 15))[3] == 0  # original transparent pixel
    assert img.getpixel((25, 25)) == (10, 200, 10, 255)


def test_exif_orientation_is_applied():
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise when displayed
    img = Image.new("RGB", (40, 20), (0, 0, 255))
    img.paste((255, 0, 0), (0, 0, 10, 20))  # red strip on the left
    out = normalize_upload(_encode(img, "JPEG", exif=exif, quality=95))
    # displayed upright: 20 wide x 40 tall, red strip now on top
    assert out.size == (40, 40)
    r, _, b, a = out.getpixel((20, 2))
    assert a == 255 and r > 200 and b < 60


def test_too_large_data_rejected():
    with pytest.raises(ValueError, match="image_too_large"):
        normalize_upload(b"\0" * (MAX_UPLOAD_BYTES + 1))
