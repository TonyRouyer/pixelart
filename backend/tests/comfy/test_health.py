from pixelforge.comfy.client import ComfyError
from pixelforge.comfy.fake import FakeComfyClient
from pixelforge.comfy.health import HealthReport, check_comfy
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
