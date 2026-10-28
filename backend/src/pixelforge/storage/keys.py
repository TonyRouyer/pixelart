"""Storage keys (spec section 4), relative to the data directory."""

from __future__ import annotations

from pixelforge.domain.models import Direction


def _d(d: Direction | str) -> str:
    return d.value if isinstance(d, Direction) else str(d)


def project_dir(pid: str) -> str:
    return f"projects/{pid}"


def project_json(pid: str) -> str:
    return f"projects/{pid}/project.json"


def reference_input(pid: str) -> str:
    return f"projects/{pid}/reference/input.png"


def reference_image(pid: str) -> str:
    return f"projects/{pid}/reference/reference.png"


def candidate(pid: str, i: int) -> str:
    return f"projects/{pid}/reference/candidates/{i}.png"


def view_image(pid: str, d: Direction | str) -> str:
    return f"projects/{pid}/views/{_d(d)}.png"


def raw_dir(pid: str, anim: str, d: Direction | str) -> str:
    return f"projects/{pid}/animations/{anim}/{_d(d)}/raw"


def raw_frame(pid: str, anim: str, d: Direction | str, name: str) -> str:
    return f"{raw_dir(pid, anim, d)}/{name}"


def processed_frame(pid: str, anim: str, d: Direction | str, name: str) -> str:
    return f"projects/{pid}/animations/{anim}/{_d(d)}/processed/{name}"


def export_zip(pid: str, stamp: str) -> str:
    return f"projects/{pid}/exports/{stamp}.zip"
