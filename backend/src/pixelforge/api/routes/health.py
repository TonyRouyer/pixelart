import dataclasses
import logging

from fastapi import APIRouter

from pixelforge.api.deps import Health
from pixelforge.pixelart.palettes import PRESET_PALETTES

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/health")
async def get_health(health: Health) -> dict:
    """Backend status and ComfyUI readiness; never fails."""
    try:
        report = await health()
        comfy = {**dataclasses.asdict(report), "ok": report.ok}
    except Exception:
        log.exception("health check failed")
        comfy = {"comfy_reachable": False, "missing_nodes": [], "missing_models": [], "ok": False}
    return {"backend": "ok", "comfy": comfy}


@router.get("/presets/palettes")
def get_palettes() -> dict[str, list[str]]:
    """Preset palettes as ``{name: ["#rrggbb", ...]}``."""
    return {
        name: [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in colors]
        for name, colors in PRESET_PALETTES.items()
    }
