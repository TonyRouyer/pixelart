from fastapi import FastAPI
from fastapi.testclient import TestClient

from pixelforge.api.errors import install_error_handlers
from pixelforge.export.json_atlas import ExportIncomplete
from pixelforge.generation.base import GenerationError
from pixelforge.jobs.queue import JobConflict
from pixelforge.storage.projects import ProjectNotFound


def _app(exc: Exception) -> TestClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    def boom():
        raise exc

    return TestClient(app, raise_server_exceptions=False)


def _error(exc: Exception):
    r = _app(exc).get("/boom")
    return r.status_code, r.json()["error"]


def test_project_not_found():
    status, err = _error(ProjectNotFound("x"))
    assert (status, err["code"], err["hint"]) == (404, "not_found", None)


def test_job_conflict():
    status, err = _error(JobConflict("j1"))
    assert (status, err["code"]) == (409, "conflict")


def test_export_incomplete_lists_missing():
    status, err = _error(ExportIncomplete(["walk_down", "walk_up"]))
    assert (status, err["code"]) == (409, "export_incomplete")
    assert "walk_down" in err["message"] and "walk_up" in err["message"]


def test_value_error_uses_first_arg_as_code():
    status, err = _error(ValueError("unknown_frame"))
    assert (status, err["code"], err["message"]) == (400, "unknown_frame", "unknown_frame")
    _, err = _error(ValueError("bad_thing", "Explained"))
    assert (err["code"], err["message"]) == ("bad_thing", "Explained")


def test_generation_error_is_502_with_hint():
    status, err = _error(GenerationError("comfy_oom", "Out of memory", "Reduce size"))
    assert (status, err["code"], err["message"], err["hint"]) == (
        502,
        "comfy_oom",
        "Out of memory",
        "Reduce size",
    )


def test_unknown_exception_is_500_internal(caplog):
    status, err = _error(RuntimeError("secret"))
    assert (status, err["code"]) == (500, "internal")
    assert "secret" not in err["message"]
    assert any(r.exc_info for r in caplog.records)
