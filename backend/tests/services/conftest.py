import asyncio

import pytest
from svc_helpers import TIMEOUT

from pixelforge.comfy.health import check_comfy
from pixelforge.comfy.sprite_fake import SpriteFakeComfyClient
from pixelforge.config import Settings
from pixelforge.generation.pose_generator import PoseGenerator
from pixelforge.generation.reference import ComfyReferenceGenerator
from pixelforge.jobs.events import EventBus
from pixelforge.jobs.queue import Job, JobQueue, JobStatus
from pixelforge.services.projects import AnimationConfigIn, ProjectService
from pixelforge.storage.local import LocalStorage
from pixelforge.storage.projects import ProjectRepository


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, grid_canvas=256)


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(tmp_path)


@pytest.fixture
def events():
    return EventBus()


@pytest.fixture
async def jobs(storage, events):
    queue = JobQueue(storage, events)
    yield queue
    await queue.stop()


@pytest.fixture
def client():
    return SpriteFakeComfyClient()


@pytest.fixture
def make_svc(storage, events, jobs, settings):
    def make(client, health=None) -> ProjectService:
        return ProjectService(
            ProjectRepository(storage),
            storage,
            ComfyReferenceGenerator(client, settings),
            PoseGenerator(client, settings),
            jobs,
            settings,
            health=health or (lambda: check_comfy(client, settings)),
            events=events,
            interrupt=client.interrupt,
        )

    return make


@pytest.fixture
def svc(make_svc, client):
    return make_svc(client)


@pytest.fixture
def run(jobs):
    async def _run(job: Job, status: JobStatus = JobStatus.succeeded) -> Job:
        await jobs.start()

        async def poll() -> None:
            while jobs.get(job.id).status in (JobStatus.queued, JobStatus.running):
                await asyncio.sleep(0.005)

        await asyncio.wait_for(poll(), TIMEOUT)
        final = jobs.get(job.id)
        assert final.status == status, final.error
        return final

    return _run


@pytest.fixture
async def ready_views(svc, run):
    """A project with a validated reference and generated views; returns its id."""
    p = svc.create_project("Chevalier")
    await run(svc.generate_reference(p.id, "knight", n=1))
    svc.select_reference(p.id, 0)
    await run(svc.generate_views(p.id))
    return p.id


@pytest.fixture
async def walk_pid(svc, run, ready_views):
    """``ready_views`` plus a generated 6-frame walk in every direction."""
    svc.configure_animations(ready_views, [AnimationConfigIn(type="walk", frame_count=6, fps=10)])
    for j in svc.generate_animation(ready_views, "walk"):
        await run(j)
    return ready_views
