"""Application factory: wires storage, queue, generators and service, and mounts the routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pixelforge.api.errors import install_error_handlers
from pixelforge.api.routes import (
    animations,
    export,
    files,
    health,
    jobs,
    projects,
    reference,
    views,
    ws,
)
from pixelforge.comfy.client import ComfyClient, HttpComfyClient
from pixelforge.comfy.health import check_comfy
from pixelforge.config import Settings, get_settings
from pixelforge.generation.pose_generator import PoseGenerator
from pixelforge.generation.reference import ComfyReferenceGenerator
from pixelforge.jobs.events import EventBus
from pixelforge.jobs.queue import JobQueue
from pixelforge.services.projects import ProjectService
from pixelforge.storage.local import LocalStorage
from pixelforge.storage.projects import ProjectRepository


def create_app(settings: Settings | None = None, comfy: ComfyClient | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        storage = LocalStorage(settings.data_dir)
        bus = EventBus()
        queue = JobQueue(storage, bus)
        client = comfy if comfy is not None else HttpComfyClient(settings.comfy_url)

        async def health():
            return await check_comfy(client, settings)

        service = ProjectService(
            ProjectRepository(storage),
            storage,
            ComfyReferenceGenerator(client, settings),
            PoseGenerator(client, settings),
            queue,
            settings,
            health=health,
            events=bus,
            interrupt=client.interrupt,
        )
        app.state.settings = settings
        app.state.storage = storage
        app.state.bus = bus
        app.state.queue = queue
        app.state.client = client
        app.state.health = health
        app.state.service = service
        await queue.start()
        service.recover_statuses()
        try:
            yield
        finally:
            await queue.stop()

    app = FastAPI(title="PixelForge", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    for module in (health, projects, reference, views, animations, jobs, files, export, ws):
        app.include_router(module.router, prefix="/api")
    return app
