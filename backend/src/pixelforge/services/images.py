"""Normalization of user-supplied images."""

from __future__ import annotations

import io

from PIL import Image, ImageOps

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_SIDE = 1024


def normalize_upload(data: bytes) -> Image.Image:
    """Decode an uploaded image into an RGBA square of at most MAX_SIDE px.

    EXIF orientation is applied, the image is downscaled (LANCZOS) so that its longest side fits,
    then centred on a transparent square canvas.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("image_too_large")
    try:
        with Image.open(io.BytesIO(data)) as opened:
            opened.load()
            img = ImageOps.exif_transpose(opened).convert("RGBA")
    except Exception as exc:  # Pillow raises many types for undecodable input
        raise ValueError("unsupported_image") from exc
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    side = max(img.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    return canvas
