import pytest
from gen_helpers import CELL_COLORS, grid_image_with_cell_colors, input_of, sprite
from PIL import Image

from pixelforge.comfy.client import ComfyError
from pixelforge.comfy.fake import FakeComfyClient
from pixelforge.config import Settings
from pixelforge.domain.models import Direction, ViewKind
from pixelforge.generation.base import BACKGROUND_RGB, GenerationError
from pixelforge.generation.pose_generator import PoseGenerator
from pixelforge.poses.library import load_neutral


def ref():
    return sprite((200, 0, 0, 0))


def poses(n):
    return [load_neutral(ViewKind.topdown4, Direction.down)] * n


def frames(n):
    return [sprite(CELL_COLORS[i] + (255,), (336, 336)) for i in range(n)]


async def test_generate_uses_grid_and_splits():
    fake = FakeComfyClient(lambda wf: [grid_image_with_cell_colors(6, cell=336)])
    out = await PoseGenerator(fake, Settings()).generate(
        ref(), poses(6), "pixel art", 7, lambda p: None
    )
    assert len(out) == 6 and out[4].getpixel((5, 5))[:3] == CELL_COLORS[4]
    wf = fake.workflows[0]
    assert input_of(wf, "seed") == 7 and (input_of(wf, "width"), input_of(wf, "height")) == (
        1008,
        672,
    )
    assert input_of(wf, "batch") == 1
    assert fake.uploads[input_of(wf, "pose_image")].size == (1008, 672)
    assert fake.uploads[input_of(wf, "reference_image")].getpixel((0, 0)) == BACKGROUND_RGB


async def test_generate_resizes_odd_output():
    fake = FakeComfyClient(lambda wf: [grid_image_with_cell_colors(4, cell=250)])
    out = await PoseGenerator(fake, Settings()).generate(ref(), poses(4), "p", 0, lambda p: None)
    assert out[0].size == (512, 512) and out[3].getpixel((5, 5))[:3] == CELL_COLORS[3]


async def test_regenerate_frame_mask_targets_cell():
    fake = FakeComfyClient(lambda wf: [grid_image_with_cell_colors(6, cell=336)])
    out = await PoseGenerator(fake, Settings()).regenerate_frame(
        ref(), poses(6), frames(6), 2, "p", 1, lambda p: None
    )
    wf = fake.workflows[0]
    mask = fake.uploads[input_of(wf, "mask_image")]
    assert mask.size == (1008, 672) and mask.mode == "RGB"
    assert mask.getpixel((2 * 336 + 10, 10)) == (255, 255, 255)
    assert mask.getpixel((10, 10)) == (0, 0, 0)
    assert mask.getpixel((2 * 336 + 10, 336 + 10)) == (0, 0, 0)
    assert fake.uploads[input_of(wf, "source_image")].size == (1008, 672)
    assert out.getpixel((5, 5))[:3] == CELL_COLORS[2]


async def test_flattens_alpha_onto_background():
    fake = FakeComfyClient(lambda wf: [grid_image_with_cell_colors(4, cell=256)])
    transparent = [Image.new("RGBA", (64, 64), (255, 0, 0, 0))] * 4
    await PoseGenerator(fake, Settings()).regenerate_frame(
        ref(), poses(4), transparent, 0, "p", 1, lambda p: None
    )
    src = fake.uploads[input_of(fake.workflows[0], "source_image")]
    assert src.getpixel((100, 100)) == BACKGROUND_RGB


async def test_uploads_are_unique_per_call():
    fake = FakeComfyClient(lambda wf: [grid_image_with_cell_colors(4, cell=256)])
    gen = PoseGenerator(fake, Settings())
    await gen.generate(ref(), poses(4), "p", 0, lambda p: None)
    await gen.generate(ref(), poses(4), "p", 0, lambda p: None)
    assert len(fake.uploads) == 4


async def test_oom_becomes_generation_error():
    def boom(wf):
        raise ComfyError("oom", "CUDA out of memory")

    with pytest.raises(GenerationError) as e:
        await PoseGenerator(FakeComfyClient(boom), Settings()).generate(
            ref(), poses(4), "p", 0, lambda p: None
        )
    assert e.value.code == "gpu_oom" and e.value.hint
