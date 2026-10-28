"""Single-worker GPU job queue; jobs run strictly one at a time."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel

from pixelforge.generation.base import GenerationError
from pixelforge.jobs.events import EventBus
from pixelforge.storage.base import Storage

log = logging.getLogger(__name__)

JOBS_KEY = "jobs.json"
MAX_JOBS = 200
PERSIST_PROGRESS_STEP = 0.1

JobFn = Callable[["JobContext"], Awaitable[None]]
CancelHook = Callable[[], Awaitable[None]]


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


_ACTIVE = (JobStatus.queued, JobStatus.running)


class Job(BaseModel):
    id: str
    kind: str
    project_id: str
    target: str
    status: JobStatus = JobStatus.queued
    progress: float = 0.0
    error: dict | None = None
    created_at: datetime
    finished_at: datetime | None = None


class JobConflict(Exception):
    """A queued or running job already targets an overlapping resource."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"job {job_id} already targets an overlapping resource")
        self.job_id = job_id


class JobContext:
    def __init__(self, queue: JobQueue, job_id: str) -> None:
        self._queue = queue
        self._job_id = job_id

    def progress(self, value: float) -> None:
        self._queue._set_progress(self._job_id, value)

    def on_cancel(self, cb: CancelHook) -> None:
        hooks = self._queue._hooks.get(self._job_id)
        if hooks is not None:  # job already finished: nothing left to interrupt
            hooks.append(cb)


def _overlaps(a: str, b: str) -> bool:
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


class JobQueue:
    def __init__(self, storage: Storage, events: EventBus) -> None:
        self._storage = storage
        self._events = events
        self._jobs: dict[str, Job] = {}
        self._fns: dict[str, JobFn] = {}
        self._hooks: dict[str, list[CancelHook]] = {}
        self._pending: asyncio.Queue[str] = asyncio.Queue()
        self._persisted_progress: dict[str, float] = {}
        self._worker: asyncio.Task | None = None
        self._current: tuple[str, asyncio.Task] | None = None
        self._recovered = False
        self._cancelling: set[str] = set()

    # -- public API -------------------------------------------------------

    def submit(self, kind: str, project_id: str, target: str, fn: JobFn) -> Job:
        for other in self._jobs.values():
            if (
                other.project_id == project_id
                and other.status in _ACTIVE
                and _overlaps(other.target, target)
            ):
                raise JobConflict(other.id)
        job = Job(
            id=uuid4().hex,
            kind=kind,
            project_id=project_id,
            target=target,
            created_at=datetime.now(UTC),
        )
        self._jobs[job.id] = job
        self._fns[job.id] = fn
        self._hooks[job.id] = []
        self._changed(job)
        self._pending.put_nowait(job.id)
        return job.model_copy()

    def get(self, job_id: str) -> Job:
        return self._jobs[job_id].model_copy()

    def list(self, project_id: str | None = None) -> list[Job]:
        """Jobs ordered oldest first, optionally restricted to one project."""
        jobs = sorted(self._jobs.values(), key=lambda j: j.created_at)
        return [j.model_copy() for j in jobs if project_id is None or j.project_id == project_id]

    async def cancel(self, job_id: str) -> None:
        job = self._jobs[job_id]
        if job.status == JobStatus.queued:
            self._finish(job, JobStatus.cancelled)
        elif job.status == JobStatus.running and job_id not in self._cancelling:
            self._cancelling.add(job_id)
            for hook in list(self._hooks.get(job_id, [])):
                try:
                    await hook()
                except Exception:
                    log.exception("on_cancel hook failed for job %s", job_id)
            # a hook may have let the job end on its own meanwhile
            if job.status == JobStatus.running:
                self._finish(job, JobStatus.cancelled)
                if self._current and self._current[0] == job_id:
                    self._current[1].cancel()

    async def start(self) -> None:
        if self._worker is not None and not self._worker.done():
            return
        self.recover()
        self._worker = asyncio.create_task(self._run_worker())

    async def stop(self) -> None:
        worker, self._worker = self._worker, None
        if worker is None:
            return
        if self._current is not None:
            await self.cancel(self._current[0])
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)

    def recover(self) -> None:
        """Load persisted jobs; those left queued or running by a crash become failed."""
        self._recovered = True
        try:
            data = self._storage.read_json(JOBS_KEY)
        except FileNotFoundError:
            return
        changed = False
        for raw in data.get("jobs", []):
            job = Job.model_validate(raw)
            if job.id in self._jobs:
                continue
            if job.status in _ACTIVE:
                job.status = JobStatus.failed
                job.error = {
                    "code": "interrupted",
                    "message": "The server stopped before this job finished",
                    "hint": "Start the job again",
                }
                job.finished_at = datetime.now(UTC)
                changed = True
            self._jobs[job.id] = job
        if changed:
            self._persist()

    # -- internals --------------------------------------------------------

    async def _run_worker(self) -> None:
        while True:
            job_id = await self._pending.get()
            job = self._jobs.get(job_id)
            if job is None or job.status != JobStatus.queued:
                continue  # cancelled while waiting
            try:
                await self._execute(job)
            except Exception:  # backstop: the worker must outlive any single job
                log.exception("unexpected error while running job %s", job_id)
                if job.status in _ACTIVE:
                    self._finish(
                        job, JobStatus.failed, {"code": "internal", "message": "worker error"}
                    )

    async def _execute(self, job: Job) -> None:
        task: asyncio.Future | None = None
        try:
            job.status = JobStatus.running
            self._changed(job)
            task = asyncio.ensure_future(self._fns[job.id](JobContext(self, job.id)))
            self._current = (job.id, task)
            await asyncio.wait({task})
        except asyncio.CancelledError:  # the worker itself is being stopped
            if task is not None and not task.done():
                task.cancel()
            if job.status == JobStatus.running:
                self._finish(job, JobStatus.cancelled)
            raise
        except Exception as e:  # the callable could not even be started
            log.exception("job %s could not start", job.id)
            if job.status == JobStatus.running:
                self._finish(job, JobStatus.failed, {"code": "internal", "message": str(e)})
            return
        finally:
            self._current = None
        if job.status != JobStatus.running:
            return  # already finalised by cancel()
        if task.cancelled():
            self._finish(job, JobStatus.cancelled)
            return
        exc = task.exception()
        if exc is None:
            job.progress = 1.0
            self._finish(job, JobStatus.succeeded)
        elif job.id in self._cancelling:  # e.g. the interrupt hook made the job raise
            self._finish(job, JobStatus.cancelled)
        elif isinstance(exc, GenerationError):
            error = {"code": exc.code, "message": exc.message, "hint": exc.hint}
            self._finish(job, JobStatus.failed, error)
        else:
            log.error("job %s failed", job.id, exc_info=exc)
            self._finish(job, JobStatus.failed, {"code": "internal", "message": str(exc)})

    def _finish(self, job: Job, status: JobStatus, error: dict | None = None) -> None:
        job.status = status
        job.error = error
        job.finished_at = datetime.now(UTC)
        self._fns.pop(job.id, None)
        self._hooks.pop(job.id, None)
        self._cancelling.discard(job.id)
        self._changed(job)

    def _set_progress(self, job_id: str, value: float) -> None:
        job = self._jobs.get(job_id)
        if job is None or job.status != JobStatus.running:
            return
        job.progress = min(1.0, max(0.0, value))
        self._events.publish({"type": "job", "job": job.model_dump(mode="json")})
        last = self._persisted_progress.get(job_id, 0.0)
        if abs(job.progress - last) >= PERSIST_PROGRESS_STEP - 1e-9:
            self._persist()

    def _changed(self, job: Job) -> None:
        self._events.publish({"type": "job", "job": job.model_dump(mode="json")})
        self._persist()

    def _persist(self) -> None:
        if not self._recovered:
            self.recover()  # never overwrite history left by a previous run
        recent = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        for old in recent[MAX_JOBS:]:
            if old.status not in _ACTIVE:
                del self._jobs[old.id]
                self._persisted_progress.pop(old.id, None)
        jobs = sorted(self._jobs.values(), key=lambda j: j.created_at)
        for j in jobs:
            self._persisted_progress[j.id] = j.progress
        try:
            self._storage.write_json(JOBS_KEY, {"jobs": [j.model_dump(mode="json") for j in jobs]})
        except OSError:
            log.exception("could not persist %s", JOBS_KEY)
