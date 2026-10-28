"""Project repository on top of a Storage."""

from __future__ import annotations

import re
import secrets

from pixelforge.domain.models import Project
from pixelforge.storage import keys
from pixelforge.storage.base import Storage
from pixelforge.text import slugify


class ProjectNotFound(LookupError):
    def __init__(self, pid: str) -> None:
        super().__init__(f"project not found: {pid}")
        self.pid = pid


class ProjectRepository:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def create(self, name: str, output_size: int = 64, style_prompt: str | None = None) -> Project:
        extra = {"style_prompt": style_prompt} if style_prompt is not None else {}
        project = Project(
            id=f"{slugify(name)}-{secrets.token_hex(2)}",
            name=name,
            seed=secrets.randbelow(2**31),
            output_size=output_size,
            **extra,
        )
        self.save(project)
        return project

    def get(self, pid: str) -> Project:
        key = keys.project_json(pid)
        if not self._storage.exists(key):
            raise ProjectNotFound(pid)
        return Project.model_validate(self._storage.read_json(key))

    def save(self, project: Project) -> None:
        self._storage.write_json(keys.project_json(project.id), project.model_dump(mode="json"))

    def list(self) -> list[Project]:
        found = self._storage.list("projects")
        return [
            Project.model_validate(self._storage.read_json(k))
            for k in found
            if re.fullmatch(r"projects/[^/]+/project\.json", k)
        ]

    def delete(self, pid: str) -> None:
        self._storage.delete_prefix(keys.project_dir(pid))
