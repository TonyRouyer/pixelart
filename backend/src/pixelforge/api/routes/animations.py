from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from pixelforge.api.deps import Service
from pixelforge.domain.models import Direction, Project
from pixelforge.jobs.queue import Job
from pixelforge.services.projects import AnimationConfigIn, PreviewOut

router = APIRouter()


class GenerateAnimation(BaseModel):
    directions: list[Direction] | None = None


class FramesBody(BaseModel):
    frames: list[str]


@router.post("/projects/{pid}/animations")
async def configure_animations(pid: str, body: list[AnimationConfigIn], svc: Service) -> Project:
    return svc.configure_animations(pid, body)


@router.post("/projects/{pid}/animations/{anim}/generate", status_code=202)
async def generate_animation(
    pid: str, anim: str, svc: Service, body: GenerateAnimation | None = None
) -> list[Job]:
    return svc.generate_animation(pid, anim, body.directions if body else None)


@router.post("/projects/{pid}/animations/{anim}/{direction}/frames/{i}/regenerate", status_code=202)
async def regenerate_frame(pid: str, anim: str, direction: Direction, i: int, svc: Service) -> Job:
    """Regenerate one frame. ``i`` is the raw file number (``003.png`` -> 3), not the position
    of the frame in the ordered ``frames`` list."""
    return svc.regenerate_frame(pid, anim, direction, i)


@router.put("/projects/{pid}/animations/{anim}/{direction}/frames")
async def set_frames(
    pid: str, anim: str, direction: Direction, body: FramesBody, svc: Service
) -> Project:
    """Set the ordered list of raw frame files (e.g. ``["000.png", "002.png"]``) to keep."""
    return svc.set_frames(pid, anim, direction, body.frames)


@router.post("/projects/{pid}/animations/{anim}/{direction}/frames/{i}/import")
async def import_frame(
    pid: str, anim: str, direction: Direction, i: int, file: UploadFile, svc: Service
) -> Project:
    """Replace one frame with an uploaded image. ``i`` is the raw file number (``003.png`` -> 3),
    not the position of the frame in the ordered ``frames`` list."""
    return svc.import_frame(pid, anim, direction, i, await file.read())


@router.get("/projects/{pid}/preview/{anim}/{direction}")
async def preview(pid: str, anim: str, direction: Direction, svc: Service) -> PreviewOut:
    return svc.preview(pid, anim, direction)
