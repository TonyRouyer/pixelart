from fastapi import APIRouter

from pixelforge.api.deps import Service
from pixelforge.jobs.queue import Job

router = APIRouter()


@router.get("/jobs")
async def list_jobs(svc: Service, project_id: str | None = None) -> list[Job]:
    return svc.jobs.list(project_id)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, svc: Service) -> Job:
    return svc.jobs.get(job_id)  # unknown id: KeyError -> 404


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str, svc: Service) -> Job:
    """Cancel a job (restoring the statuses it had marked as generating)."""
    svc.jobs.get(job_id)  # unknown id: KeyError -> 404
    await svc.cancel_job(job_id)
    return svc.jobs.get(job_id)
