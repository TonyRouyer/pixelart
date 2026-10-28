import pytest
from gen_helpers import CELL_COLORS, grid_image_with_cell_colors, input_of, sprite
from PIL import Image

from pixelforge.comfy.client import ComfyError
from pixelforge.comfy.fake import FakeComfyClient
from pixelforge.config import Settings
from pixelforge.domain.models import DIRECTION_ORDER, Direction, ViewKind
from pixelforge.generation.base import (
    BACKGROUND_RGB,
    NEGATIVE_PROMPT,
    SPRITE_SUFFIX,
    GenerationError,
)
from pixelforge.generation.reference import ComfyReferenceGenerator


async def test_from_prompt_uses_txt2img_batch():
    fake = FakeComfyClient(lambda wf: [sprite() for _ in range(3)])
    out = await ComfyReferenceGenerator(fake, Settings()).from_prompt("a knight", 3, 11)
    assert len(out) == 3
    wf = fake.workflows[0]
    assert input_of(wf, "batch") == 3 and input_of(wf, "seed") == 11
    assert (input_of(wf, "width"), input_of(wf, "height")) == (1024, 1024)
    assert input_of(wf, "positive") == f"a knight, {SPRITE_SUFFIX}"
    assert input_of(wf, "negative") == NEGATIVE_PROMPT


async def test_remove_background_returns_rgba():
    fake = FakeComfyClient(lambda wf: [Image.new("RGB", (8, 8), (1, 2, 3))])
    out = await ComfyReferenceGenerator(fake, Settings()).remove_background(sprite())
    assert out.mode == "RGBA" and out.getpixel((0, 0)) == (1, 2, 3, 255)
    assert input_of(fake.workflows[0], "source_image") in fake.uploads


async def test_turnaround_returns_four_directions():
    fake = FakeComfyClient(lambda wf: [grid_image_with_cell_colors(4, cell=250)])
    ref = Image.new("RGBA", (32, 32), (255, 0, 0, 0))
    out = await ComfyReferenceGenerator(fake, Settings()).turnaround(ref, ViewKind.topdown4, 5)
    assert list(out) == list(DIRECTION_ORDER) == [d for d in Direction]
    assert out[Direction.right].getpixel((5, 5))[:3] == CELL_COLORS[2]
    assert out[Direction.up].size == (512, 512)
    wf = fake.workflows[0]
    assert (input_of(wf, "width"), input_of(wf, "height")) == (1024, 1024)
    assert input_of(wf, "batch") == 1 and input_of(wf, "seed") == 5
    assert fake.uploads[input_of(wf, "pose_image")].size == (1024, 1024)
    assert fake.uploads[input_of(wf, "reference_image")].getpixel((0, 0)) == BACKGROUND_RGB


async def test_comfy_errors_are_converted():
    def boom(wf):
        raise ComfyError("unreachable", "down")

    with pytest.raises(GenerationError) as e:
        await ComfyReferenceGenerator(FakeComfyClient(boom), Settings()).from_prompt("x", 1, 0)
    assert e.value.code == "comfy_unreachable" and e.value.hint


@pytest.mark.parametrize(
    ("kind", "code"),
    [("oom", "gpu_oom"), ("execution", "comfy_execution"), ("interrupted", "cancelled")],
)
def test_from_comfy_codes(kind, code):
    err = GenerationError.from_comfy(ComfyError(kind, "m"))
    assert err.code == code and err.message
    assert (err.hint is None) == (kind in ("execution", "interrupted"))
