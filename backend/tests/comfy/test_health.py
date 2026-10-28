import httpx
import pytest

from pixelforge.comfy.client import ComfyError, HttpComfyClient
from pixelforge.comfy.fake import FakeComfyClient
from pixelforge.comfy.health import HealthReport, cached_health, check_comfy
from pixelforge.comfy.workflows import all_required_nodes
from pixelforge.config import Settings


async def test_health_reports_missing():
    fake = FakeComfyClient(lambda wf: [], object_info={"KSampler": {}}, models={"checkpoints": []})
    r = await check_comfy(fake, Settings())
    assert (
        not r.ok
        and "IPAdapterAdvanced" in r.missing_nodes
        and Settings().checkpoint in r.missing_models
    )


async def test_health_ok_with_default_fake():
    r = await check_comfy(FakeComfyClient(lambda wf: []), Settings())
    assert r == HealthReport(comfy_reachable=True, missing_nodes=[], missing_models=[])
    assert r.ok


async def test_health_lists_each_missing_model():
    s = Settings()
    fake = FakeComfyClient(lambda wf: [], models={"checkpoints": [s.checkpoint]})
    r = await check_comfy(fake, s)
    assert r.comfy_reachable and r.missing_nodes == []
    assert r.missing_models == [s.lora, s.controlnet_openpose]


async def test_health_unreachable():
    class Down(FakeComfyClient):
        async def object_info(self) -> dict:
            raise ComfyError("unreachable", "connection refused")

    r = await check_comfy(Down(lambda wf: []), Settings())
    assert r == HealthReport(comfy_reachable=False, missing_nodes=[], missing_models=[])
    assert not r.ok


OLD_COMFY = "ComfyUI trop ancien : mettez-le à jour (route /models absente)"


async def test_health_old_comfy_without_models_route():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/object_info":
            return httpx.Response(200, json={n: {} for n in all_required_nodes()})
        return httpx.Response(404)

    client = HttpComfyClient("http://comfy.test", transport=httpx.MockTransport(handler))
    r = await check_comfy(client, Settings())
    assert r.comfy_reachable and r.missing_nodes == []
    assert r.missing_models == [OLD_COMFY] and not r.ok


async def test_health_other_http_errors_still_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/object_info":
            return httpx.Response(200, json={})
        return httpx.Response(500)

    client = HttpComfyClient("http://comfy.test", transport=httpx.MockTransport(handler))
    with pytest.raises(ComfyError) as e:
        await check_comfy(client, Settings())
    assert e.value.kind == "execution"


async def test_cached_health_reuses_report_for_five_seconds():
    calls = []
    now = [100.0]

    async def check():
        calls.append(now[0])
        return HealthReport(comfy_reachable=True, missing_nodes=[], missing_models=[])

    health = cached_health(check, ttl=5.0, clock=lambda: now[0])
    first = await health()
    now[0] = 104.9
    assert await health() is first and calls == [100.0]
    now[0] = 105.0
    await health()
    assert calls == [100.0, 105.0]


async def test_cached_health_does_not_cache_errors():
    calls = []

    async def check():
        calls.append(1)
        raise ComfyError("execution", "boom")

    health = cached_health(check, ttl=5.0, clock=lambda: 0.0)
    for _ in range(2):
        with pytest.raises(ComfyError):
            await health()
    assert len(calls) == 2
