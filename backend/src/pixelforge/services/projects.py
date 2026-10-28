"""Project orchestration: the operations behind the HTTP API.

Synchronous methods validate and update the project at once; GPU work is submitted to the
``JobQueue`` and returns a ``Job``. Every saved change is published on the ``EventBus`` as
``{"type": "project", "project": <Project>}``.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable

from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from pixelforge.config import Settings
from pixelforge.domain.models import (
    DIRECTION_ORDER,
    AnimationConfig,
    AnimationType,
    Direction,
    PixelSettings,
    Project,
)
from pixelforge.generation.pose_generator import AnimationGenerator
from pixelforge.generation.reference import ReferenceGenerator
from pixelforge.jobs.events import EventBus
from pixelforge.jobs.queue import Job, JobConflict, JobContext, JobQueue, JobStatus
from pixelforge.pixelart.palettes import PRESET_PALETTES
from pixelforge.poses.library import load_clip, load_neutral
from pixelforge.poses.model import sample
from pixelforge.services import processing
from pixelforge.services.gpu_jobs import GpuJobs, Health, Interrupt, JobBody
from pixelforge.services.images import normalize_upload
from pixelforge.storage import keys
from pixelforge.storage.base import Storage
from pixelforge.storage.projects import ProjectNotFound, ProjectRepository

_GENERATED_VIEW = ("generated", "validated")


class AnimationConfigIn(BaseModel):
    type: AnimationType
    frame_count: int = Field(ge=2, le=16)
    fps: int = Field(ge=1, le=60)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    style_prompt: str | None = None
    output_size: int | None = Field(default=None, ge=16, le=256)
    pixel_settings: PixelSettings | None = None
    mirror_right: bool | None = None


class PreviewOut(BaseModel):
    fps: int
    loop: bool
    frames: list[str]


def _new_seed(project: Project, first: bool) -> int:
    """The project seed for a first generation, a fresh one for a re-generation."""
    return project.seed if first else secrets.randbelow(2**31)


class ProjectService:
    def __init__(
        self,
        repo: ProjectRepository,
        storage: Storage,
        ref_gen: ReferenceGenerator,
        anim_gen: AnimationGenerator,
        jobs: JobQueue,
        settings: Settings,
        health: Health,
        events: EventBus,
        interrupt: Interrupt | None = None,
    ) -> None:
        self.repo = repo
        self.storage = storage
        self.ref_gen = ref_gen
        self.anim_gen = anim_gen
        self.jobs = jobs
        self.settings = settings
        self._events = events
        self._gpu = GpuJobs(jobs, health, interrupt)

    # -- projects ---------------------------------------------------------

    def create_project(
        self, name: str, output_size: int = 64, style_prompt: str | None = None
    ) -> Project:
        project = self.repo.create(name, output_size, style_prompt)
        self._publish(project)
        return project

    def update_project(self, pid: str, patch: ProjectPatch) -> Project:
        p = self.repo.get(pid)
        ps = patch.pixel_settings
        if (
            ps is not None
            and ps.palette.mode == "preset"
            and ps.palette.preset not in PRESET_PALETTES
        ):
            raise ValueError("unknown_palette")
        before = (p.output_size, p.pixel_settings)
        for field in patch.model_fields_set:
            value = getattr(patch, field)
            if value is not None:
                setattr(p, field, value)
        if (p.output_size, p.pixel_settings) != before:
            processing.reprocess(self.storage, p)  # before saving: a failure changes nothing
        return self._save(p)

    def delete_project(self, pid: str) -> None:
        """Delete a project; ``JobConflict`` while one of its jobs is queued or running."""
        self.repo.get(pid)
        for job in self.jobs.list(pid):
            if job.status in (JobStatus.queued, JobStatus.running):
                raise JobConflict(job.id)
        self.repo.delete(pid)

    # -- reference --------------------------------------------------------

    def upload_reference(self, pid: str, data: bytes) -> Project:
        p = self.repo.get(pid)
        img = normalize_upload(data)

        async def body(ctx: JobContext) -> None:
            self._store_candidates(pid, [await self.ref_gen.remove_background(img)])

        self._gpu.submit("remove_bg", pid, "reference", body)
        self.storage.write_image(keys.reference_input(pid), img)
        return p

    def generate_reference(self, pid: str, prompt: str, n: int = 4) -> Job:
        p = self.repo.get(pid)
        if n < 1:
            raise ValueError("invalid_count")
        seed = _new_seed(p, p.reference.status == "none")

        async def body(ctx: JobContext) -> None:
            images = await self.ref_gen.from_prompt(prompt, n, seed)
            ctx.progress(0.5)
            cut = []
            for i, img in enumerate(images):
                cut.append(await self.ref_gen.remove_background(img))
                ctx.progress(0.5 + 0.5 * (i + 1) / len(images))
            self._store_candidates(pid, cut)

        return self._gpu.submit("generate_reference", pid, "reference", body)

    def select_reference(self, pid: str, index: int) -> Project:
        p = self.repo.get(pid)
        if not 0 <= index < len(p.reference.candidates):
            raise ValueError("unknown_candidate")
        self._gpu.ensure_free(pid, "reference")
        data = self.storage.read_bytes(p.reference.candidates[index])
        self.storage.write_bytes(keys.reference_image(pid), data)
        p.reference.status = "validated"
        return self._save(p)

    def _store_candidates(self, pid: str, images: list[Image.Image]) -> None:
        self.storage.delete_prefix(keys.candidates_dir(pid))
        for i, img in enumerate(images):
            self.storage.write_image(keys.candidate(pid, i), img.convert("RGBA"))
        p = self.repo.get(pid)
        p.reference.status = "candidates"
        p.reference.candidates = [keys.candidate(pid, i) for i in range(len(images))]
        self._save(p)

    # -- views ------------------------------------------------------------

    def generate_views(self, pid: str, direction: Direction | None = None) -> Job:
        p = self.repo.get(pid)
        if p.reference.status != "validated":
            raise ValueError("reference_not_validated")
        if direction is not None:
            if any(p.views[d] not in _GENERATED_VIEW for d in DIRECTION_ORDER):
                raise ValueError("views_not_generated")
            if direction == Direction.right and p.mirror_right:
                raise ValueError("right_is_mirrored")
        first = all(s == "pending" for s in p.views.values())
        seed = _new_seed(p, first and direction is None)

        async def body(ctx: JobContext) -> None:
            cur = self.repo.get(pid)
            ref = self.storage.read_image(keys.reference_image(pid))
            if direction is None:
                views = await self.ref_gen.turnaround(ref, cur.view, seed)
            else:
                current = [
                    self.storage.read_image(keys.view_image(pid, d)) for d in DIRECTION_ORDER
                ]
                poses = [load_neutral(cur.view, d) for d in DIRECTION_ORDER]
                index = DIRECTION_ORDER.index(direction)
                img = await self.anim_gen.regenerate_frame(
                    ref, poses, current, index, cur.style_prompt, seed, ctx.progress
                )
                views = {direction: img}
            cur = self.repo.get(pid)
            if cur.mirror_right and Direction.left in views:
                views[Direction.right] = ImageOps.mirror(views[Direction.left])
            for d, img in views.items():
                self.storage.write_image(keys.view_image(pid, d), img.convert("RGBA"))
                cur.views[d] = "generated"
            self._save(cur)

        target = "views" if direction is None else f"views/{direction.value}"
        return self._gpu.submit("views", pid, target, body)

    def validate_view(self, pid: str, d: Direction) -> Project:
        p = self.repo.get(pid)
        if p.views[d] not in _GENERATED_VIEW:
            raise ValueError("view_not_generated")
        self._gpu.ensure_free(pid, f"views/{d.value}")
        p.views[d] = "validated"
        return self._save(p)

    # -- animations -------------------------------------------------------

    def configure_animations(self, pid: str, configs: list[AnimationConfigIn]) -> Project:
        """Set the complete list of animations.

        Animations absent from ``configs`` are deleted with their frames (``JobConflict`` while
        one of their jobs is active); the project is then reprocessed (shared auto palette).
        """
        p = self.repo.get(pid)
        wanted = {c.type.value for c in configs}
        removed = [a.id for a in p.animations if a.id not in wanted]
        self._gpu.ensure_free(pid, *removed)
        for c in configs:
            try:
                anim = p.animation(c.type.value)
            except KeyError:
                anim = AnimationConfig.from_type(c.type)
                anim.frame_count, anim.fps = c.frame_count, c.fps
                p.animations.append(anim)
                continue
            if anim.frame_count != c.frame_count:
                anim.frame_count = c.frame_count
                for d, state in anim.directions.items():
                    if state.status in ("ready", "stale"):
                        count = len(processing.raw_names(self.storage, pid, anim.id, d))
                        state.status = "ready" if count == c.frame_count else "stale"
            anim.fps = c.fps
        if removed:
            p.animations = [a for a in p.animations if a.id in wanted]
            for anim_id in removed:
                self.storage.delete_prefix(keys.animation_dir(pid, anim_id))
            processing.reprocess(self.storage, p)
        return self._save(p)

    def generate_animation(
        self, pid: str, anim_id: str, directions: list[Direction] | None = None
    ) -> list[Job]:
        p = self.repo.get(pid)
        anim = p.animation(anim_id)
        dirs = list(dict.fromkeys(directions or DIRECTION_ORDER))
        for d in dirs:
            if p.views[d] not in _GENERATED_VIEW:
                raise ValueError("view_not_generated")
        self._gpu.ensure_free(pid, *(f"{anim_id}/{d.value}" for d in dirs))
        submitted = []
        for d in dirs:
            prev = anim.directions[d].status
            body = self._animation_body(pid, anim_id, d, _new_seed(p, prev == "empty"))
            restore = self._direction_restorer(pid, anim_id, d, prev)
            submitted.append(
                self._gpu.submit("animation", pid, f"{anim_id}/{d.value}", body, restore)
            )
            anim.directions[d].status = "generating"
        self._save(p)
        return submitted

    def _animation_body(self, pid: str, anim_id: str, d: Direction, seed: int) -> JobBody:
        async def body(ctx: JobContext) -> None:
            p = self.repo.get(pid)
            anim = p.animation(anim_id)
            view = self.storage.read_image(keys.view_image(pid, d))
            poses = sample(load_clip(p.view, anim.type, d), anim.frame_count)
            frames = await self.anim_gen.generate(view, poses, p.style_prompt, seed, ctx.progress)
            self.storage.delete_prefix(keys.raw_dir(pid, anim_id, d))
            names = [f"{i:03d}.png" for i in range(len(frames))]
            for name, img in zip(names, frames, strict=True):
                self.storage.write_image(keys.raw_frame(pid, anim_id, d, name), img.convert("RGBA"))
            p = self.repo.get(pid)
            processing.reprocess(self.storage, p, anim_id)
            state = p.animation(anim_id).directions[d]
            state.frames, state.status = names, "ready"
            self._save(p)

        return body

    def regenerate_frame(self, pid: str, anim_id: str, d: Direction, index: int) -> Job:
        """Inpaint raw frame ``index`` (file ``<index:03d>.png``) of one direction."""
        p = self.repo.get(pid)
        anim = p.animation(anim_id)
        names = processing.raw_names(self.storage, pid, anim_id, d)
        name = f"{index:03d}.png"
        if index < 0 or name not in names:
            raise ValueError("unknown_frame")
        target = f"{anim_id}/{d.value}/{index}"
        self._gpu.ensure_free(pid, target)
        prev = anim.directions[d].status
        seed = _new_seed(p, False)

        async def body(ctx: JobContext) -> None:
            cur = self.repo.get(pid)
            clip = load_clip(cur.view, cur.animation(anim_id).type, d)
            view = self.storage.read_image(keys.view_image(pid, d))
            frames = [self.storage.read_image(keys.raw_frame(pid, anim_id, d, n)) for n in names]
            img = await self.anim_gen.regenerate_frame(
                view, sample(clip, len(names)), frames, names.index(name), cur.style_prompt,
                seed, ctx.progress,
            )  # fmt: skip
            self.storage.write_image(keys.raw_frame(pid, anim_id, d, name), img.convert("RGBA"))
            cur = self.repo.get(pid)
            processing.reprocess(self.storage, cur, anim_id)
            cur.animation(anim_id).directions[d].status = "stale" if prev == "stale" else "ready"
            self._save(cur)

        restore = self._direction_restorer(pid, anim_id, d, prev)
        job = self._gpu.submit("frame", pid, target, body, restore)
        anim.directions[d].status = "generating"
        self._save(p)
        return job

    def set_frames(self, pid: str, anim_id: str, d: Direction, frames: list[str]) -> Project:
        p = self.repo.get(pid)
        state = p.animation(anim_id).directions[d]
        names = set(processing.raw_names(self.storage, pid, anim_id, d))
        if not frames or len(set(frames)) != len(frames) or not set(frames) <= names:
            raise ValueError("invalid_frames")
        self._gpu.ensure_free(pid, f"{anim_id}/{d.value}")
        state.frames = list(frames)
        return self._save(p)

    def import_frame(
        self, pid: str, anim_id: str, d: Direction, index: int, data: bytes
    ) -> Project:
        p = self.repo.get(pid)
        p.animation(anim_id)
        name = f"{index:03d}.png"
        if index < 0 or name not in processing.raw_names(self.storage, pid, anim_id, d):
            raise ValueError("unknown_frame")
        self._gpu.ensure_free(pid, f"{anim_id}/{d.value}")
        img = normalize_upload(data)
        key = keys.raw_frame(pid, anim_id, d, name)
        size = self.storage.read_image(key).size
        self.storage.write_image(key, img.resize(size, Image.Resampling.LANCZOS))
        processing.reprocess(self.storage, p, anim_id)
        self._publish(p)
        return p

    # -- processing -------------------------------------------------------

    def reprocess(self, pid: str, anim_id: str | None = None) -> None:
        processing.reprocess(self.storage, self.repo.get(pid), anim_id)

    def preview(self, pid: str, anim_id: str, d: Direction) -> PreviewOut:
        p = self.repo.get(pid)
        anim = p.animation(anim_id)
        return PreviewOut(
            fps=anim.fps, loop=anim.loop, frames=processing.preview_keys(p, anim_id, d)
        )

    def export(self, pid: str) -> str:
        return processing.export_zip(self.storage, self.repo.get(pid))

    # -- jobs -------------------------------------------------------------

    def recover_statuses(self) -> None:
        """Settle directions left "generating" by a crash (call after ``JobQueue.start``).

        A direction with no active job on its target becomes "ready" when it has
        ``frame_count`` raw frames, "stale" when it has some, "empty" otherwise; its frame list
        is reset to the raw files when it names missing ones, and the project is reprocessed.
        """
        for p in self.repo.list():
            changed = False
            for anim in p.animations:
                for d, state in anim.directions.items():
                    if state.status != "generating":
                        continue
                    if self._gpu.busy(p.id, f"{anim.id}/{d.value}") is not None:
                        continue
                    names = processing.raw_names(self.storage, p.id, anim.id, d)
                    if not state.frames or not set(state.frames) <= set(names):
                        state.frames = names
                    if not names:
                        state.status = "empty"
                    else:
                        state.status = "ready" if len(names) == anim.frame_count else "stale"
                    changed = True
            if changed:
                processing.reprocess(self.storage, p)
                self._save(p)

    async def cancel_job(self, job_id: str) -> None:
        """Cancel a job and restore what it had marked as generating, even if it never ran."""
        await self._gpu.cancel(job_id)

    def _direction_restorer(
        self, pid: str, anim_id: str, d: Direction, prev: str
    ) -> Callable[[], None]:
        def restore() -> None:
            try:
                p = self.repo.get(pid)
                state = p.animation(anim_id).directions[d]
            except (ProjectNotFound, KeyError):
                return
            if state.status == "generating":
                state.status = prev  # type: ignore[assignment]
                self._save(p)

        return restore

    def _save(self, project: Project) -> Project:
        self.repo.save(project)
        self._publish(project)
        return project

    def _publish(self, project: Project) -> None:
        self._events.publish({"type": "project", "project": project.model_dump(mode="json")})
