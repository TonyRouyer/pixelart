"""End-to-end run against a real ComfyUI with a GPU.

Run with ``pytest -m gpu`` on the machine where ComfyUI is running (see docs/setup-comfyui.md).
It is deselected by default and fails (never skips) when ComfyUI is unreachable.
"""

import asyncio
import io
import time
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pixelforge.api.app import create_app
from pixelforge.comfy.client import ComfyError, HttpComfyClient
from pixelforge.config import Settings

pytestmark = pytest.mark.gpu

JOB_TIMEOUT_S = 900.0  # first run loads the SDXL checkpoint, ControlNet and IP-Adapter


def _wait_job(client: TestClient, job_id: str) -> dict:
    end = time.monotonic() + JOB_TIMEOUT_S
    while time.monotonic() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(1.0)
    raise AssertionError(f"job {job_id} did not finish within {JOB_TIMEOUT_S:.0f}s")


def _assert_job_ok(job: dict) -> None:
    assert job["status"] == "succeeded", f"job failed: {job}"


def _assert_background_removed(data_dir, pid: str) -> None:
    """No background leftovers on the left, right and bottom 1-px border of processed frames.

    The top row is exempt: fit_to_cell may legitimately put the head of a tall character there.
    """
    frames = sorted((data_dir / "projects" / pid / "animations" / "walk").glob("*/processed/*.png"))
    assert len(frames) == 24, frames
    for path in frames:
        with Image.open(path) as img:
            alpha = np.array(img.convert("RGBA"))[..., 3]
        border = np.concatenate([alpha[:, 0], alpha[:, -1], alpha[-1, :]])
        assert border.max() == 0, f"opaque border pixels in {path.relative_to(data_dir)}"


def test_prompt_to_walk_sheet_export(tmp_path):
    settings = Settings(data_dir=tmp_path)
    comfy = HttpComfyClient(settings.comfy_url)
    try:
        asyncio.run(comfy.object_info())
    except ComfyError as exc:
        if exc.kind != "unreachable":
            raise
        pytest.fail(
            f"comfy_unreachable: ComfyUI does not answer on {settings.comfy_url} ({exc}). "
            "Start ComfyUI (run_nvidia_gpu.bat) or set PIXELFORGE_COMFY_URL, then retry."
        )

    with TestClient(create_app(settings, comfy)) as client:
        health = client.get("/api/health").json()["comfy"]
        assert not health["missing_nodes"], f"missing ComfyUI nodes: {health['missing_nodes']}"
        assert not health["missing_models"], f"missing models: {health['missing_models']}"

        pid = client.post("/api/projects", json={"name": "GPU e2e", "output_size": 64}).json()["id"]

        r = client.post(
            f"/api/projects/{pid}/reference/generate",
            json={"prompt": "pixel art knight with a blue tunic", "n": 1},
        )
        assert r.status_code == 202, r.text
        _assert_job_ok(_wait_job(client, r.json()["id"]))
        r = client.post(f"/api/projects/{pid}/reference/select", json={"index": 0})
        assert r.status_code == 200, r.text

        r = client.post(f"/api/projects/{pid}/views/generate")
        assert r.status_code == 202, r.text
        _assert_job_ok(_wait_job(client, r.json()["id"]))
        for direction in ("down", "left", "right", "up"):
            r = client.post(f"/api/projects/{pid}/views/{direction}/validate")
            assert r.status_code == 200, r.text

        r = client.post(
            f"/api/projects/{pid}/animations",
            json=[{"type": "walk", "frame_count": 6, "fps": 10}],
        )
        assert r.status_code == 200, r.text
        r = client.post(f"/api/projects/{pid}/animations/walk/generate", json={})
        assert r.status_code == 202, r.text
        jobs = r.json()
        assert len(jobs) == 4
        for job in jobs:
            _assert_job_ok(_wait_job(client, job["id"]))
        _assert_background_removed(tmp_path, pid)

        r = client.post(f"/api/projects/{pid}/export")
        assert r.status_code == 200, r.text
        zipped = client.get(r.json()["url"])
        assert zipped.status_code == 200

    with zipfile.ZipFile(io.BytesIO(zipped.content)) as z:
        names = z.namelist()
        walk_png = [n for n in names if n.endswith("/walk.png")]
        assert len(walk_png) == 1 and walk_png[0].replace("walk.png", "walk.json") in names, names
        with Image.open(io.BytesIO(z.read(walk_png[0]))) as sheet:
            # 6 frames x 64 px wide, 4 directions x 64 px high
            assert sheet.size == (384, 256)
