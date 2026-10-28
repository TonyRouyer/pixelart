import pytest
from PIL import Image

from pixelforge.comfy.health import check_comfy
from pixelforge.comfy.sprite_fake import SpriteFakeComfyClient
from pixelforge.config import Settings
from pixelforge.domain.models import (
    DIRECTION_ORDER,
    AnimationType,
    Direction,
    ViewKind,
)
from pixelforge.generation.base import BACKGROUND_RGB
from pixelforge.generation.pose_generator import PoseGenerator
from pixelforge.generation.reference import ComfyReferenceGenerator
from pixelforge.poses.library import load_clip, load_neutral
from pixelforge.poses.model import sample


def assert_sprite(img: Image.Image) -> None:
    """A colored rectangle centred on the flat gray background."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    for corner in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        assert rgb.getpixel(corner) == BACKGROUND_RGB
    assert rgb.getpixel((w // 2, h // 2)) != BACKGROUND_RGB


async def test_txt2img_returns_batch_of_requested_size():
    out = await ComfyReferenceGenerator(SpriteFakeComfyClient(), Settings()).from_prompt("k", 3, 1)
    assert len(out) == 3 and all(i.size == (1024, 1024) for i in out)
    for img in out:
        assert_sprite(img)


async def test_remove_background_keys_out_gray():
    client = SpriteFakeComfyClient()
    gen = ComfyReferenceGenerator(client, Settings())
    [img] = await gen.from_prompt("k", 1, 1)
    out = await gen.remove_background(img)
    assert out.mode == "RGBA" and out.size == img.size
    assert out.getpixel((0, 0))[3] == 0 and out.getpixel((512, 512))[3] == 255


async def test_turnaround_one_sprite_per_direction():
    gen = ComfyReferenceGenerator(SpriteFakeComfyClient(), Settings(grid_canvas=256))
    views = await gen.turnaround(Image.new("RGBA", (64, 64)), ViewKind.topdown4, 1)
    assert list(views) == list(DIRECTION_ORDER)
    for img in views.values():
        assert img.size == (128, 128)
        assert_sprite(img)


@pytest.mark.parametrize("n", [2, 3, 4, 6, 8, 12, 13, 16])
@pytest.mark.parametrize("canvas", [256, 1024])
async def test_pose_grid_one_sprite_per_cell(n, canvas):
    clip = load_clip(ViewKind.topdown4, AnimationType.walk, Direction.down)
    gen = PoseGenerator(SpriteFakeComfyClient(), Settings(grid_canvas=canvas))
    frames = await gen.generate(Image.new("RGBA", (64, 64)), sample(clip, n), "s", 1, lambda p: 0)
    assert len(frames) == n
    for f in frames:
        assert_sprite(f)


async def test_inpaint_changes_only_the_masked_cell():
    neutral = [load_neutral(ViewKind.topdown4, d) for d in DIRECTION_ORDER]
    gen = PoseGenerator(SpriteFakeComfyClient(), Settings(grid_canvas=256))
    frames = [Image.new("RGBA", (128, 128), (200, 0, 0, 255)) for _ in range(4)]
    out = await gen.regenerate_frame(
        Image.new("RGBA", (64, 64)), neutral, frames, 2, "s", 1, lambda p: 0
    )
    assert out.size == (128, 128)
    assert_sprite(out)


async def test_health_ok_by_default():
    assert (await check_comfy(SpriteFakeComfyClient(), Settings())).ok
