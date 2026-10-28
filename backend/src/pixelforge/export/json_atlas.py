"""PNG sheet + JSON atlas export (Aseprite-like, consumed by the Godot loader)."""

from __future__ import annotations

import io
import json
import zipfile
from importlib import resources
from pathlib import Path
from typing import Any

from pixelforge.domain.models import DIRECTION_ORDER, AnimationConfig, Project
from pixelforge.export.sheet import ProcessedAnimation, build_sheet
from pixelforge.text import slugify


class ExportIncomplete(Exception):
    """Raised when the project cannot be exported yet; `missing` is "<anim>_<dir>" entries."""

    def __init__(self, missing: list[str], message: str | None = None) -> None:
        self.missing = missing
        super().__init__(message or f"export incomplete, not ready: {', '.join(missing)}")


def build_animation_json(
    anim: AnimationConfig,
    frames: ProcessedAnimation,
    size: int,
    padding: int,
    anchor: tuple[int, int],
    image_name: str,
) -> dict[str, Any]:
    step = size + padding
    duration = round(1000 / anim.fps)
    atlas: dict[str, Any] = {}
    tags: list[dict[str, Any]] = []
    index = 0
    for row, direction in enumerate(DIRECTION_ORDER):
        count = len(frames.get(direction, []))
        if count == 0:
            continue
        name = f"{anim.id}_{direction.value}"
        for col in range(count):
            atlas[f"{name}_{col}"] = {
                "frame": {"x": col * step, "y": row * step, "w": size, "h": size},
                "duration": duration,
            }
        tags.append({"name": name, "from": index, "to": index + count - 1, "direction": "forward"})
        index += count
    sheet_w = max((len(frames.get(d, [])) for d in DIRECTION_ORDER), default=0) * step - padding
    return {
        "frames": atlas,
        "meta": {
            "image": image_name,
            "size": {"w": max(sheet_w, 0), "h": len(DIRECTION_ORDER) * step - padding},
            "frameTags": tags,
            "x_autosprite": {
                "animation": anim.id,
                "fps": anim.fps,
                "loop": anim.loop,
                "frame_size": size,
                "anchor": {"x": anchor[0], "y": anchor[1]},
                "rows": [d.value for d in DIRECTION_ORDER],
            },
        },
    }


def build_character_json(project: Project, animations: list[AnimationConfig]) -> dict[str, Any]:
    ax, ay = project.anchor()
    return {
        "name": project.name,
        "view": project.view.value,
        "frame_size": project.output_size,
        "anchor": {"x": ax, "y": ay},
        "directions": [d.value for d in DIRECTION_ORDER],
        "animations": [
            {
                "name": a.id,
                "image": f"{a.id}.png",
                "data": f"{a.id}.json",
                "fps": a.fps,
                "loop": a.loop,
                "frame_count": a.frame_count,
            }
            for a in animations
        ],
    }


def _missing(project: Project) -> list[str]:
    missing: list[str] = []
    for anim in project.animations:
        for direction in DIRECTION_ORDER:
            state = anim.directions[direction]
            if state.status != "ready" or not state.frames:
                missing.append(f"{anim.id}_{direction.value}")
    return missing


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


class JsonAtlasExporter:
    def export(self, project: Project, processed: dict[str, ProcessedAnimation], out: Path) -> Path:
        if not project.animations:
            raise ExportIncomplete([], "nothing to export: the project has no animation")
        missing = _missing(project)
        if missing:
            raise ExportIncomplete(missing)
        for anim in project.animations:
            if anim.id not in processed:
                raise ValueError(f"no processed frames for ready animation {anim.id!r}")

        root = slugify(project.name)
        size, padding = project.output_size, project.pixel_settings.padding
        loader = (
            resources.files("pixelforge.export") / "godot" / "load_spriteframes.gd"
        ).read_text(encoding="utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(
                f"{root}/character.json", _dump(build_character_json(project, project.animations))
            )
            for anim in project.animations:
                frames = processed[anim.id]
                png = io.BytesIO()
                build_sheet(frames, size, padding).save(png, format="PNG")
                z.writestr(f"{root}/{anim.id}.png", png.getvalue())
                data = build_animation_json(
                    anim, frames, size, padding, project.anchor(), f"{anim.id}.png"
                )
                z.writestr(f"{root}/{anim.id}.json", _dump(data))
            z.writestr(f"{root}/godot/load_spriteframes.gd", loader)
        tmp.replace(out)
        return out
