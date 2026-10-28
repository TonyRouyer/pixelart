"""Pixel-art processing of stored frames: reprocess, preview keys and ZIP export."""

from __future__ import annotations

from datetime import UTC, datetime

from pixelforge.domain.models import DIRECTION_ORDER, Direction, Project
from pixelforge.export.json_atlas import JsonAtlasExporter
from pixelforge.export.sheet import ProcessedAnimation
from pixelforge.pixelart.palettes import character_palette
from pixelforge.pixelart.pipeline import Frames, finalize_animation, prepare_animation
from pixelforge.storage import keys
from pixelforge.storage.base import Storage


def raw_names(storage: Storage, pid: str, anim_id: str, d: Direction) -> list[str]:
    """File names of the raw frames of one direction, sorted."""
    prefix = keys.raw_dir(pid, anim_id, d) + "/"
    names = [k[len(prefix) :] for k in storage.list(prefix.rstrip("/"))]
    return [n for n in names if n.endswith(".png") and "/" not in n]


def reprocess(storage: Storage, project: Project, anim_id: str | None = None) -> None:
    """Rebuild processed/ frames from raw/ with one palette for the whole character.

    The palette is always computed from the prepared frames of every animation that has raw
    frames. In ``auto`` palette mode that palette changes with any raw frame, so every animation
    is finalized again; with a preset/custom palette only ``anim_id`` (all when None) is.
    """
    if anim_id is not None:
        project.animation(anim_id)  # KeyError for an unknown animation
    if anim_id is None or project.pixel_settings.palette.mode == "auto":
        targets = [a.id for a in project.animations]
    else:
        targets = [anim_id]
    pid, settings = project.id, project.pixel_settings
    size, anchor = project.output_size, project.anchor()

    prepared: dict[str, tuple[dict[Direction, list[str]], Frames]] = {}
    for anim in project.animations:
        names = {d: raw_names(storage, pid, anim.id, d) for d in DIRECTION_ORDER}
        names = {d: ns for d, ns in names.items() if ns}
        if not names:
            continue
        raw = {
            d: [storage.read_image(keys.raw_frame(pid, anim.id, d, n)) for n in ns]
            for d, ns in names.items()
        }
        prepared[anim.id] = (names, prepare_animation(raw, settings, size, anchor))

    every_frame = [f for _, frames in prepared.values() for fs in frames.values() for f in fs]
    palette = character_palette(every_frame, settings)

    for t in targets:
        if t not in prepared:
            continue
        names, frames = prepared[t]
        final = finalize_animation(frames, settings, palette)
        for d in DIRECTION_ORDER:
            storage.delete_prefix(keys.processed_dir(pid, t, d))
        for d, images in final.items():
            for name, img in zip(names[d], images, strict=True):
                storage.write_image(keys.processed_frame(pid, t, d, name), img)


def preview_keys(project: Project, anim_id: str, d: Direction) -> list[str]:
    """Storage keys of the processed frames of one direction, in playback order."""
    state = project.animation(anim_id).directions[d]
    return [keys.processed_frame(project.id, anim_id, d, name) for name in state.frames]


def export_zip(storage: Storage, project: Project) -> str:
    """Write the export ZIP and return its storage key (``ExportIncomplete`` propagates)."""
    processed: dict[str, ProcessedAnimation] = {}
    for anim in project.animations:
        processed[anim.id] = {
            d: [storage.read_image(k) for k in preview_keys(project, anim.id, d)]
            for d, state in anim.directions.items()
            if state.status == "ready"
        }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    key = keys.export_zip(project.id, stamp)
    JsonAtlasExporter().export(project, processed, storage.path(key))
    return key
