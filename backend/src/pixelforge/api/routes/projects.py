from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from pixelforge.api.deps import Service
from pixelforge.domain.models import Project
from pixelforge.services.projects import ProjectPatch

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)
    output_size: int = Field(default=64, ge=16, le=256)
    style_prompt: str | None = None


@router.get("/projects")
def list_projects(svc: Service) -> list[Project]:
    return svc.repo.list()


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, svc: Service) -> Project:
    return svc.create_project(body.name, body.output_size, body.style_prompt)


@router.get("/projects/{pid}")
def get_project(pid: str, svc: Service) -> Project:
    return svc.repo.get(pid)


@router.patch("/projects/{pid}")
def patch_project(pid: str, body: ProjectPatch, svc: Service) -> Project:
    return svc.update_project(pid, body)


@router.delete("/projects/{pid}", status_code=204)
def delete_project(pid: str, svc: Service) -> Response:
    svc.repo.get(pid)  # 404 when unknown
    svc.repo.delete(pid)
    return Response(status_code=204)
