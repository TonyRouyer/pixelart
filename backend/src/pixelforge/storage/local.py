"""Filesystem-backed storage with atomic writes."""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from PIL import Image


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._resolved_root = self.root.resolve()

    def path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if p != self._resolved_root and not p.is_relative_to(self._resolved_root):
            raise ValueError(f"key escapes storage root: {key!r}")
        return p

    def read_bytes(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def write_bytes(self, key: str, data: bytes) -> None:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            try:
                tmp.write(data)
            except BaseException:
                tmp.close()
                tmp_path.unlink(missing_ok=True)
                raise
        # the temp file is closed here, which os.replace requires on Windows
        try:
            os.replace(tmp_path, target)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    def read_json(self, key: str) -> dict:
        return json.loads(self.read_bytes(key).decode("utf-8"))

    def write_json(self, key: str, data: dict) -> None:
        text = json.dumps(data, indent=2, ensure_ascii=False)
        self.write_bytes(key, text.encode("utf-8"))

    def read_image(self, key: str) -> Image.Image:
        with Image.open(io.BytesIO(self.read_bytes(key))) as im:
            return im.convert("RGBA")

    def write_image(self, key: str, img: Image.Image) -> None:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        self.write_bytes(key, buf.getvalue())

    def exists(self, key: str) -> bool:
        return self.path(key).exists()

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> None:
        p = self.path(prefix)
        if p == self._resolved_root:
            raise ValueError("refusing to delete the storage root")
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink(missing_ok=True)

    def list(self, prefix: str) -> list[str]:
        base = self.path(prefix)
        if base.is_file():
            files = [base]
        elif base.is_dir():
            files = [f for f in base.rglob("*") if f.is_file()]
        else:
            return []
        return sorted(f.relative_to(self._resolved_root).as_posix() for f in files)
