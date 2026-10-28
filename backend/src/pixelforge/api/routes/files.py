from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from pixelforge.api.deps import Storage
from pixelforge.api.errors import error_response

router = APIRouter()


@router.get("/files/{key:path}", response_model=None)
def get_file(key: str, storage: Storage) -> FileResponse | JSONResponse:
    """Serve a file of the data directory; only keys under ``projects/`` are reachable."""
    if (
        not key.startswith("projects/")
        or ".." in key
        or "\\" in key
        or key.startswith("/")
        or "\x00" in key
    ):
        return error_response(400, "invalid_key", "Invalid file key")
    try:
        path = storage.path(key)
    except ValueError:
        return error_response(400, "invalid_key", "Invalid file key")
    if not path.is_file():
        return error_response(404, "not_found", f"file not found: {key}")
    return FileResponse(path, headers={"Cache-Control": "no-cache"})
