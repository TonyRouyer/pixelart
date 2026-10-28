"""FastAPI dependencies reading the components stored on ``app.state`` by the lifespan."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from starlette.requests import HTTPConnection

from pixelforge.comfy.health import HealthReport
from pixelforge.jobs.events import EventBus
from pixelforge.services.projects import ProjectService
from pixelforge.storage.local import LocalStorage


def get_service(conn: HTTPConnection) -> ProjectService:
    return conn.app.state.service


def get_bus(conn: HTTPConnection) -> EventBus:
    return conn.app.state.bus


def get_storage(conn: HTTPConnection) -> LocalStorage:
    return conn.app.state.storage


def get_health(conn: HTTPConnection) -> Callable[[], Awaitable[HealthReport]]:
    return conn.app.state.health


Service = Annotated[ProjectService, Depends(get_service)]
Bus = Annotated[EventBus, Depends(get_bus)]
Storage = Annotated[LocalStorage, Depends(get_storage)]
Health = Annotated[Callable[[], Awaitable[HealthReport]], Depends(get_health)]
