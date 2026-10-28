from fastapi import APIRouter, UploadFile
from pydantic import BaseModel, Field

from pixelforge.api.deps import Service
from pixelforge.domain.models import Project
from pixelforge.jobs.queue import Job

router = APIRouter()


class GenerateReference(BaseModel):
    prompt: str = Field(min_length=1)
    n: int = Field(default=4, ge=1, le=16)


class SelectReference(BaseModel):
    index: int


class UploadResult(BaseModel):
    project: Project
    job: Job


@router.post("/projects/{pid}/reference/upload", status_code=202)
async def upload_reference(pid: str, file: UploadFile, svc: Service) -> UploadResult:
    """Store the uploaded image and queue its background removal."""
    project = svc.upload_reference(pid, await file.read())
    job = svc.jobs.list(pid)[-1]  # the remove_bg job just submitted (no await in between)
    return UploadResult(project=project, job=job)


@router.post("/projects/{pid}/reference/generate", status_code=202)
async def generate_reference(pid: str, body: GenerateReference, svc: Service) -> Job:
    return svc.generate_reference(pid, body.prompt, body.n)


@router.post("/projects/{pid}/reference/select")
async def select_reference(pid: str, body: SelectReference, svc: Service) -> Project:
    return svc.select_reference(pid, body.index)
