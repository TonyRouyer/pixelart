"""Check that ComfyUI is reachable and has every node and model PixelForge needs."""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pixelforge.comfy.client import ComfyClient, ComfyError
from pixelforge.comfy.workflows import all_required_nodes
from pixelforge.config import Settings

OLD_COMFY = "ComfyUI trop ancien : mettez-le à jour (route /models absente)"


@dataclass(frozen=True)
class HealthReport:
    comfy_reachable: bool
    missing_nodes: list[str]
    missing_models: list[str]

    @property
    def ok(self) -> bool:
        return self.comfy_reachable and not self.missing_nodes and not self.missing_models


async def _missing_models(client: ComfyClient, settings: Settings) -> list[str]:
    missing = []
    for folder, name in (
        ("checkpoints", settings.checkpoint),
        ("loras", settings.lora),
        ("controlnet", settings.controlnet_openpose),
    ):
        try:
            available = await client.models(folder)
        except ComfyError as exc:
            if exc.kind == "execution" and exc.status == 404:
                return [OLD_COMFY]  # no /models route: the models cannot be checked
            raise
        if name not in available:
            missing.append(name)
    return missing


async def check_comfy(client: ComfyClient, settings: Settings) -> HealthReport:
    needed = all_required_nodes()
    try:
        available = await client.object_info()
        missing_models = await _missing_models(client, settings)
    except ComfyError as exc:
        if exc.kind != "unreachable":
            raise
        return HealthReport(comfy_reachable=False, missing_nodes=[], missing_models=[])
    return HealthReport(
        comfy_reachable=True,
        missing_nodes=sorted(needed - set(available)),
        missing_models=missing_models,
    )


def cached_health(
    check: Callable[[], Awaitable[HealthReport]],
    ttl: float = 5.0,
    clock: Callable[[], float] = time.monotonic,
) -> Callable[[], Awaitable[HealthReport]]:
    """Wrap ``check`` so a report is reused for ``ttl`` seconds; errors are not cached."""
    cache: tuple[float, HealthReport] | None = None

    async def health() -> HealthReport:
        nonlocal cache
        if cache is not None and clock() - cache[0] < ttl:
            return cache[1]
        report = await check()
        cache = (clock(), report)
        return report

    return health
