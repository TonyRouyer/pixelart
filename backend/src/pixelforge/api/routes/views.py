from fastapi import APIRouter
from pydantic import BaseModel

from pixelforge.api.deps import Service
from pixelforge.domain.models import Direction, Project
from pixelforge.jobs.queue import Job

router = APIRouter()


class GenerateViews(BaseModel):
    direction: Direction | None = None


@router.post("/projects/{pid}/views/generate", status_code=202)
def generate_views(pid: str, svc: Service, body: GenerateViews | None = None) -> Job:
    return svc.generate_views(pid, body.direction if body else None)


@router.post("/projects/{pid}/views/{direction}/validate")
def validate_view(pid: str, direction: Direction, svc: Service) -> Project:
    return svc.validate_view(pid, direction)
