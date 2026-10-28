import io
from unittest.mock import ANY

from PIL import Image

from pixelforge.jobs.queue import JobStatus


def png(color=(200, 50, 50, 255), size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, format="PNG")
    return buf.getvalue()


def wait_job(client, job_id, timeout=20.0):
    import time

    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def close_ws(client, ws, timeout=5.0):
    """Close a test socket and wait until the route finished unsubscribing.

    Starlette's TestClient cancels the app task right after queueing the disconnect; if the
    handler is still cleaning up, that cancellation surfaces as a CancelledError in the test.
    """
    import time

    ws.close()
    end = time.monotonic() + timeout
    while client.app.state.bus.subscriber_count and time.monotonic() < end:
        time.sleep(0.01)
    assert client.app.state.bus.subscriber_count == 0


def make_project(client, **extra) -> str:
    return client.post("/api/projects", json={"name": "Chevalier", **extra}).json()["id"]


def validated_project(client) -> str:
    pid = make_project(client)
    r = client.post(f"/api/projects/{pid}/reference/generate", json={"prompt": "knight", "n": 2})
    assert r.status_code == 202
    assert wait_job(client, r.json()["id"])["status"] == "succeeded"
    assert (
        client.post(f"/api/projects/{pid}/reference/select", json={"index": 0}).status_code == 200
    )
    return pid


def test_create_and_get_project(client):
    r = client.post("/api/projects", json={"name": "Chevalier"})
    assert r.status_code == 201
    assert client.get(f"/api/projects/{r.json()['id']}").json()["output_size"] == 64


def test_list_patch_delete_project(client):
    pid = make_project(client)
    assert [p["id"] for p in client.get("/api/projects").json()] == [pid]
    r = client.patch(f"/api/projects/{pid}", json={"name": "Renamed", "output_size": 32})
    assert (r.json()["name"], r.json()["output_size"]) == ("Renamed", 32)
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_patch_unknown_palette_is_400(client):
    pid = make_project(client)
    ps = client.get(f"/api/projects/{pid}").json()["pixel_settings"]
    ps["palette"] = {**ps["palette"], "mode": "preset", "preset": "nope"}
    r = client.patch(f"/api/projects/{pid}", json={"pixel_settings": ps})
    assert (r.status_code, r.json()["error"]["code"]) == (400, "unknown_palette")


def test_not_found_format(client):
    assert client.get("/api/projects/nope").json() == {
        "error": {"code": "not_found", "message": ANY, "hint": None}
    }


def test_invalid_output_size(client):
    r = client.post("/api/projects", json={"name": "x", "output_size": 4})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"


def test_generate_returns_202_and_ws_progress(client):
    pid = make_project(client)
    with client.websocket_connect("/api/ws") as ws:
        r = client.post(f"/api/projects/{pid}/reference/generate", json={"prompt": "knight"})
        assert r.status_code == 202
        job_id = r.json()["id"]
        seen = []
        while True:
            event = ws.receive_json()
            seen.append(event["type"])
            job = event.get("job", {})
            if job.get("id") == job_id and job["status"] in ("succeeded", "failed"):
                assert job["status"] == "succeeded"
                break
        close_ws(client, ws)
    assert "job" in seen


def test_upload_reference_returns_project_and_job(client):
    pid = make_project(client)
    r = client.post(
        f"/api/projects/{pid}/reference/upload", files={"file": ("a.png", png(), "image/png")}
    )
    assert r.status_code == 202
    body = r.json()
    assert body["project"]["id"] == pid
    assert wait_job(client, body["job"]["id"])["status"] == "succeeded"
    assert client.get(f"/api/projects/{pid}").json()["reference"]["status"] == "candidates"


def test_upload_bad_image_is_400(client):
    pid = make_project(client)
    r = client.post(
        f"/api/projects/{pid}/reference/upload", files={"file": ("a.png", b"junk", "image/png")}
    )
    assert r.status_code == 400


def test_views_require_validated_reference(client):
    pid = make_project(client)
    r = client.post(f"/api/projects/{pid}/views/generate")
    assert (r.status_code, r.json()["error"]["code"]) == (400, "reference_not_validated")


def test_full_flow_to_preview_and_export(client):
    pid = validated_project(client)
    job = client.post(f"/api/projects/{pid}/views/generate").json()
    assert wait_job(client, job["id"])["status"] == "succeeded"
    for d in ("down", "left", "right", "up"):
        assert client.post(f"/api/projects/{pid}/views/{d}/validate").status_code == 200
    r = client.post(
        f"/api/projects/{pid}/animations",
        json=[{"type": "idle", "frame_count": 4, "fps": 6}],
    )
    assert r.status_code == 200
    jobs = client.post(f"/api/projects/{pid}/animations/idle/generate", json={}).json()
    assert len(jobs) == 4
    for j in jobs:
        assert wait_job(client, j["id"])["status"] == "succeeded"
    prev = client.get(f"/api/projects/{pid}/preview/idle/down").json()
    assert prev["fps"] == 6 and len(prev["frames"]) == 4
    assert client.get(f"/api/files/{prev['frames'][0]}").status_code == 200

    # frame routes: raw file number
    r = client.post(f"/api/projects/{pid}/animations/idle/down/frames/2/regenerate")
    assert r.status_code == 202
    assert wait_job(client, r.json()["id"])["status"] == "succeeded"
    r = client.put(
        f"/api/projects/{pid}/animations/idle/down/frames",
        json={"frames": ["000.png", "001.png", "002.png"]},
    )
    assert r.status_code == 200
    r = client.post(
        f"/api/projects/{pid}/animations/idle/down/frames/1/import",
        files={"file": ("f.png", png(), "image/png")},
    )
    assert r.status_code == 200
    r = client.post(f"/api/projects/{pid}/animations/idle/down/frames/99/regenerate")
    assert r.json()["error"]["code"] == "unknown_frame"

    r = client.post(f"/api/projects/{pid}/export")
    assert r.status_code == 200
    out = r.json()
    assert out["url"] == f"/api/files/{out['key']}"
    zipped = client.get(out["url"])
    assert zipped.status_code == 200 and zipped.content[:2] == b"PK"


def test_unknown_animation_is_404(client):
    pid = make_project(client)
    r = client.get(f"/api/projects/{pid}/preview/idle/down")
    assert (r.status_code, r.json()["error"]["code"]) == (404, "not_found")


def test_jobs_routes(client):
    pid = make_project(client)
    job = client.post(f"/api/projects/{pid}/reference/generate", json={"prompt": "k"}).json()
    wait_job(client, job["id"])
    assert [j["id"] for j in client.get("/api/jobs", params={"project_id": pid}).json()] == [
        job["id"]
    ]
    assert client.get("/api/jobs", params={"project_id": "other"}).json() == []
    assert client.get("/api/jobs/zzz").status_code == 404
    assert client.delete("/api/jobs/zzz").status_code == 404


def test_delete_job_uses_service_cancel(client):
    pid = make_project(client)
    job = client.post(f"/api/projects/{pid}/reference/generate", json={"prompt": "k"}).json()
    r = client.delete(f"/api/jobs/{job['id']}")
    assert r.status_code == 200
    assert r.json()["status"] in {s.value for s in JobStatus}


def test_files_route_blocks_escape(client):
    for key in ("../../etc/passwd", "projects/../jobs.json", "projects%5C..%5Cx", "/etc/passwd"):
        r = client.get(f"/api/files/{key}")
        assert r.status_code in (400, 404)
    r = client.get("/api/files/projects/x/../../jobs.json")
    assert r.status_code in (400, 404)
    assert client.get("/api/files/projects/..%5Cjobs.json").status_code == 400
    assert client.get("/api/files/jobs.json").json()["error"]["code"] == "invalid_key"


def test_files_serves_with_no_cache_and_404(client):
    pid = make_project(client)
    assert client.get(f"/api/files/projects/{pid}/project.json").headers["cache-control"] == (
        "no-cache"
    )
    assert client.get(f"/api/files/projects/{pid}/missing.png").status_code == 404


def test_export_incomplete_409(client):
    pid = make_project(client)
    r = client.post(f"/api/projects/{pid}/export")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "export_incomplete")


def test_health_ok(client):
    body = client.get("/api/health").json()
    assert body["backend"] == "ok" and body["comfy"]["ok"] is True


def test_health_when_comfy_down(client_down):
    r = client_down.get("/api/health")
    assert r.status_code == 200
    assert r.json()["comfy"]["comfy_reachable"] is False
    assert r.json()["comfy"]["ok"] is False


def test_palette_presets(client):
    data = client.get("/api/presets/palettes").json()
    assert data["pico8"][0] == "#000000" and len(data["pico8"]) == 16


def test_cors_header(client):
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_job_progresses_without_further_requests(client):
    """A job submitted by a route must run on the event loop with no other HTTP traffic."""
    pid = make_project(client)
    with client.websocket_connect("/api/ws") as ws:
        job_id = client.post(
            f"/api/projects/{pid}/reference/generate", json={"prompt": "k"}
        ).json()["id"]
        statuses = []
        while "succeeded" not in statuses:
            event = ws.receive_json()
            if event["type"] == "job" and event["job"]["id"] == job_id:
                statuses.append(event["job"]["status"])
        close_ws(client, ws)
    assert statuses[0] == "queued" and "running" in statuses


def test_delete_project_with_active_job_is_409(client):
    import asyncio

    pid = make_project(client)
    queue = client.app.state.queue
    gate = asyncio.Event()

    async def start():
        async def hold(ctx):
            await gate.wait()

        return queue.submit("hold", pid, "reference", hold)

    job = client.portal.call(start)
    r = client.delete(f"/api/projects/{pid}")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "conflict")
    client.portal.call(lambda: gate.set())
    assert wait_job(client, job.id)["status"] == "succeeded"
    assert client.delete(f"/api/projects/{pid}").status_code == 204


def test_fake_comfy_setting_selects_sprite_fake(tmp_path, caplog):
    from fastapi.testclient import TestClient

    from pixelforge.api.app import create_app
    from pixelforge.comfy.sprite_fake import SpriteFakeComfyClient
    from pixelforge.config import Settings

    settings = Settings(_env_file=None, data_dir=tmp_path, fake_comfy=True)
    with caplog.at_level("WARNING"), TestClient(create_app(settings)) as c:
        assert isinstance(c.app.state.client, SpriteFakeComfyClient)
        assert c.get("/api/health").json()["comfy"]["ok"] is True
    assert "fake" in caplog.text.lower()


def test_health_is_cached_between_polls(settings):
    from fastapi.testclient import TestClient

    from pixelforge.api.app import create_app
    from pixelforge.comfy.sprite_fake import SpriteFakeComfyClient

    class Counting(SpriteFakeComfyClient):
        calls = 0

        async def object_info(self) -> dict:
            Counting.calls += 1
            return await super().object_info()

    with TestClient(create_app(settings, Counting())) as c:
        for _ in range(3):
            assert c.get("/api/health").json()["comfy"]["ok"] is True
    assert Counting.calls == 1
