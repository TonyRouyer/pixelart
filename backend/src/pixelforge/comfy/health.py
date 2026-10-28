"""Check that ComfyUI is reachable and has every node and model PixelForge needs."""

from dataclasses import dataclass

from pixelforge.comfy.client import ComfyClient, ComfyError
from pixelforge.comfy.workflows import all_required_nodes
from pixelforge.config import Settings


@dataclass(frozen=True)
class HealthReport:
    comfy_reachable: bool
    missing_nodes: list[str]
    missing_models: list[str]

    @property
    def ok(self) -> bool:
        return self.comfy_reachable and not self.missing_nodes and not self.missing_models


async def check_comfy(client: ComfyClient, settings: Settings) -> HealthReport:
    needed = all_required_nodes()
    try:
        available = await client.object_info()
        missing_models = [
            name
            for folder, name in (
                ("checkpoints", settings.checkpoint),
                ("loras", settings.lora),
                ("controlnet", settings.controlnet_openpose),
            )
            if name not in await client.models(folder)
        ]
    except ComfyError as exc:
        if exc.kind != "unreachable":
            raise
        return HealthReport(comfy_reachable=False, missing_nodes=[], missing_models=[])
    return HealthReport(
        comfy_reachable=True,
        missing_nodes=sorted(needed - set(available)),
        missing_models=missing_models,
    )
