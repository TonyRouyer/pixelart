import asyncio
import io

import pytest
from PIL import Image, ImageOps
from svc_helpers import TIMEOUT, BlockingClient, zip_names

from pixelforge.comfy.client import ComfyError
from pixelforge.comfy.health import HealthReport
from pixelforge.comfy.sprite_fake import SpriteFakeComfyClient
from pixelforge.domain.models import DIRECTION_ORDER, Direction, PixelSettings
from pixelforge.export.json_atlas import ExportIncomplete
from pixelforge.jobs.queue import JobConflict, JobStatus
from pixelforge.services.projects import AnimationConfigIn, ProjectPatch
from pixelforge.storage import keys
from pixelforge.storage.projects import ProjectNotFound


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def status_of(svc, pid, anim="walk", d=Direction.down) -> str:
    return svc.repo.get(pid).animation(anim).directions[d].status


# -- full flow ---------------------------------------------------------------


async def test_full_flow_to_export(svc, run, storage):
    p = svc.create_project("Chevalier")
    await run(svc.generate_reference(p.id, "knight"))
    svc.select_reference(p.id, 0)
    await run(svc.generate_views(p.id))
    svc.configure_animations(p.id, [AnimationConfigIn(type="walk", frame_count=6, fps=10)])
    for j in svc.generate_animation(p.id, "walk"):
        await run(j)
    assert svc.preview(p.id, "walk", Direction.up).frames
    key = svc.export(p.id)
    assert key.startswith(f"projects/{p.id}/exports/") and key.endswith(".zip")
    assert "chevalier/walk.png" in zip_names(storage, key)


async def test_generate_reference_writes_rgba_candidates(svc, run, storage):
    p = svc.create_project("a")
    await run(svc.generate_reference(p.id, "knight", n=3))
    ref = svc.repo.get(p.id).reference
    assert ref.status == "candidates"
    assert ref.candidates == [keys.candidate(p.id, i) for i in range(3)]
    img = storage.read_image(keys.candidate(p.id, 2))
    assert img.getpixel((0, 0))[3] == 0  # background removed
    svc.select_reference(p.id, 2)
    assert svc.repo.get(p.id).reference.status == "validated"
    assert storage.read_bytes(keys.reference_image(p.id)) == storage.read_bytes(
        keys.candidate(p.id, 2)
    )
    with pytest.raises(ValueError, match="unknown_candidate"):
        svc.select_reference(p.id, 3)


async def test_upload_reference_removes_background(svc, run, storage):
    p = svc.create_project("a")
    img = Image.new("RGB", (300, 200), (210, 210, 210))
    img.paste((200, 20, 20), (100, 50, 200, 150))
    out = svc.upload_reference(p.id, png(img))
    assert out.reference.status == "none"
    assert storage.read_image(keys.reference_input(p.id)).size == (300, 300)
    [job] = svc.jobs.list(p.id)
    assert (job.kind, job.target) == ("remove_bg", "reference")
    await run(job)
    ref = svc.repo.get(p.id).reference
    assert ref.status == "candidates" and ref.candidates == [keys.candidate(p.id, 0)]
    cand = storage.read_image(keys.candidate(p.id, 0))
    assert cand.getpixel((150, 150)) == (200, 20, 20, 255)
    assert cand.getpixel((150, 60))[3] == 0  # gray keyed out
    with pytest.raises(ValueError, match="unsupported_image"):
        svc.upload_reference(p.id, b"nope")


# -- views -------------------------------------------------------------------


async def test_views_require_validated_reference(svc, run):
    p = svc.create_project("a")
    with pytest.raises(ValueError, match="reference_not_validated"):
        svc.generate_views(p.id)
    await run(svc.generate_reference(p.id, "knight"))
    with pytest.raises(ValueError, match="reference_not_validated"):
        svc.generate_views(p.id)


async def test_views_generated_then_validated(svc, ready_views, storage):
    p = svc.repo.get(ready_views)
    assert set(p.views.values()) == {"generated"}
    for d in DIRECTION_ORDER:
        assert storage.read_image(keys.view_image(p.id, d)).mode == "RGBA"
    assert svc.validate_view(p.id, Direction.left).views[Direction.left] == "validated"


async def test_validate_pending_view_rejected(svc):
    p = svc.create_project("a")
    with pytest.raises(ValueError, match="view_not_generated"):
        svc.validate_view(p.id, Direction.down)


async def test_mirror_right(svc, run, ready_views, storage):
    svc.update_project(ready_views, ProjectPatch(mirror_right=True))
    await run(svc.generate_views(ready_views))
    left = storage.read_image(keys.view_image(ready_views, Direction.left))
    right = storage.read_image(keys.view_image(ready_views, Direction.right))
    assert right.tobytes() == ImageOps.mirror(left).tobytes()


async def test_regenerate_one_view_inpaints_the_grid(svc, run, ready_views, storage, client):
    before = {d: storage.read_bytes(keys.view_image(ready_views, d)) for d in DIRECTION_ORDER}
    svc.validate_view(ready_views, Direction.up)
    job = svc.generate_views(ready_views, Direction.up)
    assert job.target == "views/up"
    await run(job)
    wf = client.workflows[-1]
    assert any(n["class_type"] == "LoadImageMask" for n in wf.values())
    p = svc.repo.get(ready_views)
    assert p.views[Direction.up] == "generated"
    for d in (Direction.down, Direction.left, Direction.right):
        assert storage.read_bytes(keys.view_image(ready_views, d)) == before[d]
    assert storage.read_image(keys.view_image(ready_views, Direction.up)).size == (128, 128)


# -- animations --------------------------------------------------------------


async def test_generate_animation_writes_raw_and_processed(svc, walk_pid, storage):
    p = svc.repo.get(walk_pid)
    for d in DIRECTION_ORDER:
        state = p.animation("walk").directions[d]
        assert state.status == "ready"
        assert state.frames == [f"{i:03d}.png" for i in range(6)]
        for name in state.frames:
            assert storage.exists(keys.raw_frame(walk_pid, "walk", d, name))
            assert storage.read_image(keys.processed_frame(walk_pid, "walk", d, name)).size == (
                64,
                64,
            )
    preview = svc.preview(walk_pid, "walk", Direction.left)
    assert (preview.fps, preview.loop) == (10, True)
    assert preview.frames == [
        keys.processed_frame(walk_pid, "walk", Direction.left, f"{i:03d}.png") for i in range(6)
    ]


async def test_generate_animation_requires_generated_view(svc, run):
    p = svc.create_project("a")
    svc.configure_animations(p.id, [AnimationConfigIn(type="idle", frame_count=4, fps=6)])
    with pytest.raises(ValueError, match="view_not_generated"):
        svc.generate_animation(p.id, "idle", [Direction.down])
    with pytest.raises(KeyError):
        svc.generate_animation(p.id, "walk")


async def test_configure_adds_and_updates(svc):
    p = svc.create_project("a")
    p = svc.configure_animations(
        p.id,
        [
            AnimationConfigIn(type="idle", frame_count=4, fps=6),
            AnimationConfigIn(type="attack_bow", frame_count=8, fps=15),
        ],
    )
    bow = p.animation("attack_bow")
    assert (bow.frame_count, bow.fps, bow.loop) == (8, 15, False)
    p = svc.configure_animations(p.id, [AnimationConfigIn(type="idle", frame_count=4, fps=12)])
    assert [a.id for a in p.animations] == ["idle", "attack_bow"]
    assert p.animation("idle").fps == 12


async def test_frame_count_change_marks_stale(svc, walk_pid):
    pid = walk_pid
    p = svc.configure_animations(pid, [AnimationConfigIn(type="walk", frame_count=8, fps=10)])
    assert p.animation("walk").directions[Direction.down].status == "stale"
    assert len(svc.preview(pid, "walk", Direction.down).frames) == 6
    with pytest.raises(ExportIncomplete):
        svc.export(pid)


async def test_conflicting_job_rejected(svc, walk_pid):
    pid = walk_pid
    svc.generate_animation(pid, "walk", [Direction.down])
    assert status_of(svc, pid) == "generating"
    with pytest.raises(JobConflict):
        svc.regenerate_frame(pid, "walk", Direction.down, 2)
    with pytest.raises(JobConflict):
        svc.generate_animation(pid, "walk", [Direction.left, Direction.down])
    assert status_of(svc, pid, d=Direction.left) == "ready"  # nothing submitted for left
    with pytest.raises(JobConflict):
        svc.set_frames(pid, "walk", Direction.down, ["000.png"])


async def test_regenerate_frame_replaces_one_raw_frame(svc, run, walk_pid, storage):
    pid = walk_pid
    raw = [
        storage.read_bytes(keys.raw_frame(pid, "walk", Direction.down, f"{i:03d}.png"))
        for i in range(6)
    ]
    job = svc.regenerate_frame(pid, "walk", Direction.down, 2)
    assert job.target == "walk/down/2"
    assert status_of(svc, pid) == "generating"
    await run(job)
    assert status_of(svc, pid) == "ready"
    after = [
        storage.read_bytes(keys.raw_frame(pid, "walk", Direction.down, f"{i:03d}.png"))
        for i in range(6)
    ]
    assert [a == b for a, b in zip(raw, after)] == [True, True, False, True, True, True]
    with pytest.raises(ValueError, match="unknown_frame"):
        svc.regenerate_frame(pid, "walk", Direction.down, 6)


async def test_set_frames_reorders_and_drops(svc, walk_pid):
    p = svc.set_frames(walk_pid, "walk", Direction.down, ["003.png", "000.png"])
    assert p.animation("walk").directions[Direction.down].frames == ["003.png", "000.png"]
    preview = svc.preview(walk_pid, "walk", Direction.down)
    assert [k.rsplit("/", 1)[1] for k in preview.frames] == ["003.png", "000.png"]


async def test_set_frames_rejects_unknown(svc, walk_pid):
    for bad in [["000.png", "nope.png"], [], ["000.png", "000.png"], ["../project.json"]]:
        with pytest.raises(ValueError, match="invalid_frames"):
            svc.set_frames(walk_pid, "walk", Direction.down, bad)


async def test_import_frame_replaces_raw_and_reprocesses(svc, walk_pid, storage):
    pid = walk_pid
    key = keys.raw_frame(pid, "walk", Direction.down, "001.png")
    size = storage.read_image(key).size
    img = Image.new("RGBA", (500, 500), (0, 0, 0, 0))
    img.paste((0, 0, 255, 255), (150, 100, 350, 450))
    svc.import_frame(pid, "walk", Direction.down, 1, png(img))
    raw = storage.read_image(key)
    assert raw.size == size and raw.getpixel((size[0] // 2, size[1] // 2))[2] > 200
    processed = storage.read_image(keys.processed_frame(pid, "walk", Direction.down, "001.png"))
    assert processed.size == (64, 64) and processed.getbbox() is not None
    with pytest.raises(ValueError, match="unknown_frame"):
        svc.import_frame(pid, "walk", Direction.down, 9, png(img))


async def test_settings_change_reprocesses(svc, walk_pid, storage):
    svc.update_project(walk_pid, ProjectPatch(output_size=32))
    for d in DIRECTION_ORDER:
        img = storage.read_image(keys.processed_frame(walk_pid, "walk", d, "000.png"))
        assert img.size == (32, 32)


async def test_custom_palette_applies_to_every_animation(svc, run, walk_pid, storage):
    svc.configure_animations(walk_pid, [AnimationConfigIn(type="idle", frame_count=4, fps=6)])
    for j in svc.generate_animation(walk_pid, "idle"):
        await run(j)
    settings = PixelSettings.model_validate(
        {"palette": {"mode": "custom", "custom_colors": ["#ff0000", "#000000"]}}
    )
    svc.update_project(walk_pid, ProjectPatch(pixel_settings=settings))
    for anim in ("walk", "idle"):
        img = storage.read_image(keys.processed_frame(walk_pid, anim, Direction.up, "000.png"))
        colors = {c[:3] for _, c in img.getcolors(64 * 64) if c[3] > 0}
        assert colors and colors <= {(255, 0, 0), (0, 0, 0)}


async def test_reprocess_removes_stale_processed_files(svc, run, walk_pid, storage):
    svc.configure_animations(walk_pid, [AnimationConfigIn(type="walk", frame_count=4, fps=10)])
    await run(svc.generate_animation(walk_pid, "walk", [Direction.down])[0])
    names = [
        k.rsplit("/", 1)[1]
        for k in storage.list(f"projects/{walk_pid}/animations/walk/down/processed")
    ]
    assert names == [f"{i:03d}.png" for i in range(4)]


async def test_update_project_fields(svc, events):
    p = svc.create_project("a")
    sub = events.subscribe()
    first = asyncio.ensure_future(anext(sub))
    await asyncio.sleep(0)
    out = svc.update_project(p.id, ProjectPatch(name="b", style_prompt="s"))
    assert (out.name, out.style_prompt, out.id) == ("b", "s", p.id)
    event = await asyncio.wait_for(first, TIMEOUT)
    assert event == {"type": "project", "project": out.model_dump(mode="json")}
    await sub.aclose()


async def test_unknown_project(svc):
    with pytest.raises(ProjectNotFound):
        svc.update_project("missing", ProjectPatch(name="x"))


# -- failures and cancellation ----------------------------------------------


async def test_failed_job_restores_status(svc, run, ready_views, client):
    svc.configure_animations(ready_views, [AnimationConfigIn(type="walk", frame_count=6, fps=10)])

    def boom(wf):
        raise ComfyError("execution", "boom")

    client.responder = boom
    [job] = svc.generate_animation(ready_views, "walk", [Direction.down])
    assert status_of(svc, ready_views) == "generating"
    final = await run(job, JobStatus.failed)
    assert final.error["code"] == "comfy_execution"
    assert status_of(svc, ready_views) == "empty"


async def test_failed_regeneration_restores_ready(svc, run, walk_pid, client):
    client.responder = lambda wf: (_ for _ in ()).throw(ComfyError("oom", "x"))
    await run(svc.regenerate_frame(walk_pid, "walk", Direction.left, 0), JobStatus.failed)
    assert status_of(svc, walk_pid, d=Direction.left) == "ready"


async def test_job_fails_when_comfy_not_ready(make_svc, run):
    client = SpriteFakeComfyClient(models={})
    svc = make_svc(client)
    p = svc.create_project("a")
    final = await run(svc.generate_reference(p.id, "knight"), JobStatus.failed)
    assert final.error["code"] == "comfy_not_ready"
    assert "sd_xl_base_1.0.safetensors" in final.error["hint"]
    assert client.workflows == [] and client.uploads == {}


async def test_job_fails_when_comfy_unreachable(make_svc, run):
    client = SpriteFakeComfyClient()

    async def down() -> HealthReport:
        return HealthReport(comfy_reachable=False, missing_nodes=[], missing_models=[])

    svc = make_svc(client, health=down)
    p = svc.create_project("a")
    final = await run(svc.generate_reference(p.id, "knight"), JobStatus.failed)
    assert final.error["code"] == "comfy_not_ready"
    assert "ComfyUI injoignable" in final.error["hint"]
    assert client.workflows == []


async def test_cancel_running_job_interrupts_and_restores(make_svc, ready_views, jobs):
    # ``ready_views`` was built with ``svc``; a second service over the same storage blocks.
    blocking = BlockingClient()
    slow = make_svc(blocking)
    slow.configure_animations(ready_views, [AnimationConfigIn(type="walk", frame_count=6, fps=10)])
    [job] = slow.generate_animation(ready_views, "walk", [Direction.down])
    await asyncio.wait_for(blocking.started.wait(), TIMEOUT)
    await slow.cancel_job(job.id)
    assert blocking.interrupted
    assert jobs.get(job.id).status == JobStatus.cancelled
    await asyncio.sleep(0.01)
    assert status_of(slow, ready_views) == "empty"


async def test_cancel_queued_job_restores(make_svc, ready_views, jobs):
    blocking = BlockingClient()
    slow = make_svc(blocking)
    slow.configure_animations(ready_views, [AnimationConfigIn(type="walk", frame_count=6, fps=10)])
    first, second = slow.generate_animation(ready_views, "walk", [Direction.down, Direction.up])
    await jobs.start()
    await asyncio.wait_for(blocking.started.wait(), TIMEOUT)
    await slow.cancel_job(second.id)
    assert jobs.get(second.id).status == JobStatus.cancelled
    assert status_of(slow, ready_views, d=Direction.up) == "empty"
    assert status_of(slow, ready_views, d=Direction.down) == "generating"
    blocking.gate.set()

    async def done() -> None:
        while jobs.get(first.id).status != JobStatus.succeeded:
            await asyncio.sleep(0.005)

    await asyncio.wait_for(done(), TIMEOUT)
    assert status_of(slow, ready_views, d=Direction.down) == "ready"
