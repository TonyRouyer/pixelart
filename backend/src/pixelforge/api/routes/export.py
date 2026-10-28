from fastapi import APIRouter

from pixelforge.api.deps import Service

router = APIRouter()


@router.post("/projects/{pid}/export")
def export_project(pid: str, svc: Service) -> dict[str, str]:
    key = svc.export(pid)
    return {"key": key, "url": f"/api/files/{key}"}
