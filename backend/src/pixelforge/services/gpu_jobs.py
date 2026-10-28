"""Submission of GPU jobs: ComfyUI readiness check, interrupt hook and status restoration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from pixelforge.comfy.client import ComfyError
from pixelforge.comfy.health import HealthReport
from pixelforge.generation.base import GenerationError
from pixelforge.jobs.queue import (
    Job,
    JobConflict,
    JobContext,
    JobQueue,
    JobStatus,
    targets_overlap,
)

Health = Callable[[], Awaitable[HealthReport]]
Interrupt = Callable[[], Awaitable[None]]
JobBody = Callable[[JobContext], Awaitable[None]]
Restore = Callable[[], None]

_ACTIVE = (JobStatus.queued, JobStatus.running)


def not_ready_error(report: HealthReport) -> GenerationError:
    if not report.comfy_reachable:
        hint = "ComfyUI injoignable"
    else:
        parts = []
        if report.missing_nodes:
            parts.append("Nœuds manquants : " + ", ".join(report.missing_nodes))
        if report.missing_models:
            parts.append("Modèles manquants : " + ", ".join(report.missing_models))
        hint = " ; ".join(parts)
    return GenerationError("comfy_not_ready", "ComfyUI n'est pas prêt", hint)


class GpuJobs:
    def __init__(self, jobs: JobQueue, health: Health, interrupt: Interrupt | None) -> None:
        self.jobs = jobs
        self._health = health
        self._interrupt = interrupt
        self._restorers: dict[str, Restore] = {}

    def submit(
        self, kind: str, pid: str, target: str, body: JobBody, restore: Restore | None = None
    ) -> Job:
        """Queue ``body``; ``restore`` runs once if the job fails or is cancelled."""
        pending = {"restore": restore}
        job_id = ""

        def settle() -> None:
            undo = pending.pop("restore", None)
            if undo is not None:
                undo()

        async def fn(ctx: JobContext) -> None:
            if self._interrupt is not None:
                ctx.on_cancel(self._interrupt)
            try:
                await self._ensure_comfy()
                await body(ctx)
                pending.pop("restore", None)
            except BaseException:
                settle()
                raise
            finally:
                self._restorers.pop(job_id, None)

        job = self.jobs.submit(kind, pid, target, fn)
        job_id = job.id
        if restore is not None:
            self._restorers[job.id] = settle
        return job

    async def cancel(self, job_id: str) -> None:
        """Cancel a job and run its restore, even if it was cancelled before it ran."""
        await self.jobs.cancel(job_id)
        restore = self._restorers.pop(job_id, None)
        if restore is not None and self.jobs.get(job_id).status == JobStatus.cancelled:
            restore()

    def busy(self, pid: str, target: str) -> Job | None:
        """The active job of ``pid`` overlapping ``target``, if any."""
        for job in self.jobs.list(pid):
            if job.status in _ACTIVE and targets_overlap(job.target, target):
                return job
        return None

    def ensure_free(self, pid: str, *targets: str) -> None:
        """Raise ``JobConflict`` if an active job of ``pid`` overlaps one of ``targets``."""
        for t in targets:
            job = self.busy(pid, t)
            if job is not None:
                raise JobConflict(job.id)

    async def _ensure_comfy(self) -> None:
        try:
            report = await self._health()
        except ComfyError as e:
            raise GenerationError.from_comfy(e) from e
        if not report.ok:
            raise not_ready_error(report)
