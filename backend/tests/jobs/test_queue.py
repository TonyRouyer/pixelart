import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pixelforge.generation.base import GenerationError
from pixelforge.jobs.events import EventBus
from pixelforge.jobs.queue import JobConflict, JobContext, JobQueue, JobStatus
from pixelforge.storage.local import LocalStorage

TIMEOUT = 2


async def wait_idle(queue: JobQueue) -> None:
    async def poll() -> None:
        while any(j.status in (JobStatus.queued, JobStatus.running) for j in queue.list()):
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), TIMEOUT)


async def until_running(queue: JobQueue, job_id: str) -> None:
    async def poll() -> None:
        while queue.get(job_id).status != JobStatus.running:
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), TIMEOUT)


async def slow(ctx: JobContext) -> None:
    await asyncio.sleep(10)


async def _set(event: asyncio.Event) -> None:
    event.set()


def write_jobs_json(root: Path, status: str, job_id: str = "j1") -> None:
    job = {
        "id": job_id,
        "kind": "t",
        "project_id": "p",
        "target": "x",
        "status": status,
        "progress": 0.3,
        "error": None,
        "created_at": datetime.now(UTC).isoformat(),
        "finished_at": None,
    }
    (root / "jobs.json").write_text(json.dumps({"jobs": [job]}), encoding="utf-8")


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(tmp_path)


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
async def queue(storage, bus):
    q = JobQueue(storage, bus)
    await q.start()
    yield q
    await q.stop()


async def test_runs_sequentially(queue):
    order = []

    async def fn(name):
        order.append(name + "+")
        await asyncio.sleep(0.01)
        order.append(name + "-")

    queue.submit("t", "p", "a", lambda c: fn("a"))
    queue.submit("t", "p", "b", lambda c: fn("b"))
    await wait_idle(queue)
    assert order == ["a+", "a-", "b+", "b-"]


async def test_submit_returns_queued_job_with_utc_timestamp(storage, bus):
    q = JobQueue(storage, bus)  # not started: the job waits
    job = q.submit("t", "p", "a", slow)
    assert len(job.id) == 32
    assert job.status == JobStatus.queued
    assert job.progress == 0
    assert job.finished_at is None
    assert job.created_at.utcoffset() == timedelta(0)


async def test_jobs_submitted_before_start_run_after_start(storage, bus):
    q = JobQueue(storage, bus)
    ran = []

    async def fn(ctx):
        ran.append(1)

    job = q.submit("t", "p", "a", fn)
    await q.start()
    try:
        await wait_idle(q)
    finally:
        await q.stop()
    assert ran == [1]
    assert q.get(job.id).status == JobStatus.succeeded
    assert q.get(job.id).finished_at is not None


async def test_conflict_on_overlapping_target(queue):
    queue.submit("t", "p", "walk/down", slow)
    with pytest.raises(JobConflict):
        queue.submit("t", "p", "walk/down/3", slow)
    queue.submit("t", "p", "walk/up", slow)  # no conflict


async def test_conflict_when_new_target_is_parent_and_carries_job_id(queue):
    first = queue.submit("t", "p", "walk/down/3", slow)
    with pytest.raises(JobConflict) as exc:
        queue.submit("t", "p", "walk/down", slow)
    assert exc.value.job_id == first.id


async def test_no_conflict_across_projects_or_name_prefixes(queue):
    queue.submit("t", "p", "walk", slow)
    queue.submit("t", "other", "walk", slow)
    queue.submit("t", "p", "walking", slow)  # "walking" is not under "walk/"


async def test_no_conflict_once_finished(queue):
    async def quick(ctx):
        pass

    queue.submit("t", "p", "a", quick)
    await wait_idle(queue)
    queue.submit("t", "p", "a", quick)


async def test_generation_error_recorded(queue):
    async def fn(ctx):
        raise GenerationError("gpu_oom", "out of memory", "reduce frames")

    job = queue.submit("t", "p", "a", fn)
    await wait_idle(queue)
    done = queue.get(job.id)
    assert done.status == JobStatus.failed
    assert done.error == {"code": "gpu_oom", "message": "out of memory", "hint": "reduce frames"}
    assert done.finished_at is not None


async def test_unexpected_exception_recorded_as_internal(queue):
    async def fn(ctx):
        raise RuntimeError("boom")

    job = queue.submit("t", "p", "a", fn)
    await wait_idle(queue)
    assert queue.get(job.id).error == {"code": "internal", "message": "boom"}
    assert queue.get(job.id).status == JobStatus.failed


async def test_worker_survives_failure(queue):
    async def bad(ctx):
        raise RuntimeError("boom")

    async def good(ctx):
        pass

    queue.submit("t", "p", "a", bad)
    ok = queue.submit("t", "p", "b", good)
    await wait_idle(queue)
    assert queue.get(ok.id).status == JobStatus.succeeded


async def test_cancel_running_calls_hook(queue):
    called = asyncio.Event()

    async def fn(ctx):
        ctx.on_cancel(lambda: _set(called))
        await asyncio.sleep(10)

    job = queue.submit("t", "p", "x", fn)
    await until_running(queue, job.id)
    await queue.cancel(job.id)
    assert called.is_set()
    assert queue.get(job.id).status == JobStatus.cancelled
    assert queue.get(job.id).finished_at is not None


async def test_cancel_running_swallows_hook_errors_and_runs_all_hooks(queue):
    called = asyncio.Event()

    async def bad():
        raise RuntimeError("hook failed")

    async def fn(ctx):
        ctx.on_cancel(bad)
        ctx.on_cancel(lambda: _set(called))
        await asyncio.sleep(10)

    job = queue.submit("t", "p", "x", fn)
    await until_running(queue, job.id)
    await queue.cancel(job.id)
    assert called.is_set()
    assert queue.get(job.id).status == JobStatus.cancelled


async def test_next_job_runs_after_cancelling_running_one(queue):
    ran = asyncio.Event()

    async def fn(ctx):
        ran.set()

    first = queue.submit("t", "p", "a", slow)
    queue.submit("t", "p", "b", fn)
    await until_running(queue, first.id)
    await queue.cancel(first.id)
    await asyncio.wait_for(ran.wait(), TIMEOUT)


async def test_cancel_queued_never_runs(queue):
    ran = []

    async def fn(ctx):
        ran.append(1)

    first = queue.submit("t", "p", "a", slow)
    second = queue.submit("t", "p", "b", fn)
    await until_running(queue, first.id)
    await queue.cancel(second.id)
    assert queue.get(second.id).status == JobStatus.cancelled
    await queue.cancel(first.id)
    await asyncio.sleep(0.05)
    assert ran == []
    assert queue.get(second.id).status == JobStatus.cancelled


async def test_cancel_finished_is_noop_and_unknown_raises(queue):
    async def fn(ctx):
        pass

    job = queue.submit("t", "p", "a", fn)
    await wait_idle(queue)
    await queue.cancel(job.id)
    assert queue.get(job.id).status == JobStatus.succeeded
    with pytest.raises(KeyError):
        await queue.cancel("nope")
    with pytest.raises(KeyError):
        queue.get("nope")


async def test_stop_cancels_running_job(storage, bus):
    q = JobQueue(storage, bus)
    await q.start()
    await q.start()  # idempotent
    job = q.submit("t", "p", "x", slow)
    await until_running(q, job.id)
    await asyncio.wait_for(q.stop(), TIMEOUT)
    assert q.get(job.id).status == JobStatus.cancelled


async def test_recover_marks_interrupted(tmp_path):
    write_jobs_json(tmp_path, status="running")
    q = JobQueue(LocalStorage(tmp_path), EventBus())
    q.recover()
    assert q.list()[0].status == JobStatus.failed
    assert q.list()[0].error["code"] == "interrupted"
    assert q.list()[0].finished_at is not None
    persisted = json.loads((tmp_path / "jobs.json").read_text(encoding="utf-8"))
    assert persisted["jobs"][0]["status"] == "failed"


async def test_recover_marks_queued_and_keeps_finished(tmp_path):
    write_jobs_json(tmp_path, status="queued")
    q = JobQueue(LocalStorage(tmp_path), EventBus())
    q.recover()
    assert q.list()[0].error["code"] == "interrupted"
    write_jobs_json(tmp_path, status="succeeded", job_id="j2")
    q2 = JobQueue(LocalStorage(tmp_path), EventBus())
    q2.recover()
    assert q2.list()[0].status == JobStatus.succeeded
    assert q2.list()[0].error is None


async def test_start_recovers_but_not_jobs_submitted_before_start(tmp_path):
    write_jobs_json(tmp_path, status="running")
    q = JobQueue(LocalStorage(tmp_path), EventBus())
    mine = q.submit("t", "p", "a", slow)
    await q.start()
    try:
        assert q.get("j1").error["code"] == "interrupted"
        await until_running(q, mine.id)
    finally:
        await q.stop()


async def test_progress_published(queue, bus):
    events = []

    async def consume():
        async for event in bus.subscribe():
            events.append(event)
            if event["job"]["progress"] == 0.5:
                return

    consumer = asyncio.create_task(consume())

    async def poll():
        while bus.subscriber_count < 1:
            await asyncio.sleep(0)

    await asyncio.wait_for(poll(), TIMEOUT)

    async def fn(ctx):
        ctx.progress(0.5)
        await asyncio.sleep(10)

    job = queue.submit("t", "p", "a", fn)
    await asyncio.wait_for(consumer, TIMEOUT)
    assert events[-1]["type"] == "job"
    assert events[-1]["job"]["id"] == job.id
    assert events[-1]["job"]["progress"] == 0.5
    assert events[0]["job"]["status"] == "queued"
    await queue.cancel(job.id)


async def test_progress_is_clamped(queue):
    seen = []
    job_ids = []

    async def fn(ctx):
        ctx.progress(-3)
        seen.append(queue.get(job_ids[0]).progress)
        ctx.progress(7)
        seen.append(queue.get(job_ids[0]).progress)

    job_ids.append(queue.submit("t", "p", "a", fn).id)
    await wait_idle(queue)
    assert seen == [0.0, 1.0]


async def test_progress_persists_only_on_large_steps(storage, bus, queue):
    gate = asyncio.Event()
    release = asyncio.Event()

    async def fn(ctx):
        ctx.progress(0.05)
        ctx.progress(0.1)
        gate.set()
        await release.wait()

    job = queue.submit("t", "p", "a", fn)
    await asyncio.wait_for(gate.wait(), TIMEOUT)

    def persisted() -> float:
        data = storage.read_json("jobs.json")
        return next(j for j in data["jobs"] if j["id"] == job.id)["progress"]

    assert persisted() == 0.1  # 0.05 skipped, 0.1 is a 0.1 step from 0
    queue_job = queue.get(job.id)
    assert queue_job.progress == 0.1
    release.set()
    await wait_idle(queue)
    assert persisted() == 1.0  # completion always persists
    assert storage.read_json("jobs.json")["jobs"][0]["status"] == "succeeded"


async def test_state_changes_persisted(queue, storage):
    job = queue.submit("t", "p", "a", slow)
    await until_running(queue, job.id)
    assert storage.read_json("jobs.json")["jobs"][0]["status"] == "running"
    await queue.cancel(job.id)
    assert storage.read_json("jobs.json")["jobs"][0]["status"] == "cancelled"


async def test_keeps_only_200_most_recent(storage, bus):
    q = JobQueue(storage, bus)

    async def quick(ctx):
        pass

    await q.start()
    try:
        for i in range(205):
            q.submit("t", f"p{i}", "a", quick)
        await wait_idle(q)
    finally:
        await q.stop()
    assert len(q.list()) == 200
    assert len(storage.read_json("jobs.json")["jobs"]) == 200


async def test_list_filters_by_project(queue):
    queue.submit("t", "p1", "a", slow)
    queue.submit("t", "p2", "a", slow)
    assert [j.project_id for j in queue.list("p2")] == ["p2"]
    assert len(queue.list()) == 2


async def test_factory_raising_synchronously_does_not_stall_queue(queue):
    def bad(ctx):
        raise KeyError("nope")

    ran = asyncio.Event()

    async def good(ctx):
        ran.set()

    first = queue.submit("t", "p", "a", bad)
    second = queue.submit("t", "p", "b", good)
    await wait_idle(queue)
    assert queue.get(first.id).status == JobStatus.failed
    assert queue.get(first.id).error["code"] == "internal"
    assert queue.get(second.id).status == JobStatus.succeeded
    assert ran.is_set()


async def test_factory_returning_non_awaitable_fails_job(queue):
    first = queue.submit("t", "p", "a", lambda ctx: None)
    await wait_idle(queue)
    assert queue.get(first.id).status == JobStatus.failed


async def test_stop_leaves_nothing_running_when_job_ends_during_hooks(storage, bus):
    q = JobQueue(storage, bus)
    await q.start()

    async def slow_hook():
        await asyncio.sleep(0.1)

    async def x(ctx):
        ctx.on_cancel(slow_hook)
        await asyncio.sleep(0.02)  # ends on its own while stop() awaits the hook

    first = q.submit("t", "p", "x", x)
    second = q.submit("t", "p", "y", slow)
    await until_running(q, first.id)
    await asyncio.wait_for(q.stop(), TIMEOUT)
    assert q.get(first.id).status == JobStatus.succeeded
    assert q.get(second.id).status == JobStatus.cancelled
    assert not any(j.status in (JobStatus.queued, JobStatus.running) for j in q.list())
    q.submit("t", "p", "y", slow)  # no stale conflict


async def test_cancel_recorded_as_cancelled_when_fn_raises_from_interrupt(queue):
    async def fn(ctx):
        gone = asyncio.Event()

        async def interrupt():
            gone.set()
            await asyncio.sleep(0.02)

        ctx.on_cancel(interrupt)
        await gone.wait()
        raise GenerationError("cancelled", "interrupted")

    job = queue.submit("t", "p", "a", fn)
    await until_running(queue, job.id)
    await queue.cancel(job.id)
    await wait_idle(queue)
    done = queue.get(job.id)
    assert done.status == JobStatus.cancelled
    assert done.error is None


async def test_double_cancel_runs_hooks_once(queue):
    calls = []

    async def hook():
        calls.append(1)
        await asyncio.sleep(0.02)

    async def fn(ctx):
        ctx.on_cancel(hook)
        await asyncio.sleep(10)

    job = queue.submit("t", "p", "a", fn)
    await until_running(queue, job.id)
    await asyncio.gather(queue.cancel(job.id), queue.cancel(job.id))
    assert calls == [1]
    assert queue.get(job.id).status == JobStatus.cancelled


async def test_on_cancel_after_finish_is_ignored(queue):
    ctxs = []

    async def fn(ctx):
        ctxs.append(ctx)

    queue.submit("t", "p", "a", fn)
    await wait_idle(queue)
    ctxs[0].on_cancel(lambda: _set(asyncio.Event()))  # must not raise


def test_targets_overlap():
    from pixelforge.jobs.queue import targets_overlap

    assert targets_overlap("walk/down", "walk/down/2") and targets_overlap("walk", "walk/up")
    assert not targets_overlap("walk/down", "walk/downx") and not targets_overlap("a", "b")
