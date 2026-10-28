"""Mapping of domain exceptions to the ``{"error": {code, message, hint}}`` response format."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pixelforge.export.json_atlas import ExportIncomplete
from pixelforge.generation.base import GenerationError
from pixelforge.jobs.queue import JobConflict
from pixelforge.storage.projects import ProjectNotFound

log = logging.getLogger(__name__)


def error_response(status: int, code: str, message: str, hint: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message, "hint": hint}}
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProjectNotFound)
    async def _not_found(request: Request, exc: ProjectNotFound) -> JSONResponse:
        return error_response(404, "not_found", str(exc))

    @app.exception_handler(KeyError)
    async def _key_error(request: Request, exc: KeyError) -> JSONResponse:
        log.warning("KeyError on %s %s", request.method, request.url.path, exc_info=exc)
        # unknown animation / job ids surface as KeyError from the domain layer
        return error_response(404, "not_found", f"not found: {exc.args[0] if exc.args else ''}")

    @app.exception_handler(JobConflict)
    async def _conflict(request: Request, exc: JobConflict) -> JSONResponse:
        return error_response(
            409, "conflict", str(exc), "Wait for the running job or cancel it first"
        )

    @app.exception_handler(ExportIncomplete)
    async def _incomplete(request: Request, exc: ExportIncomplete) -> JSONResponse:
        return error_response(409, "export_incomplete", str(exc))

    @app.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError) -> JSONResponse:
        code = str(exc.args[0]) if exc.args else "invalid_request"
        message = str(exc.args[1]) if len(exc.args) > 1 else code
        return error_response(400, code, message)

    @app.exception_handler(GenerationError)
    async def _generation(request: Request, exc: GenerationError) -> JSONResponse:
        return error_response(502, exc.code, exc.message, exc.hint)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}".lstrip(": ")
            for e in exc.errors()
        )
        return error_response(422, "invalid_request", details or "invalid request")

    @app.exception_handler(Exception)
    async def _internal(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return error_response(500, "internal", "Internal server error")
