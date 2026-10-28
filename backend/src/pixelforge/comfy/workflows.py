"""Parameterized ComfyUI workflows in API format.

A bindable input lives on a node whose ``_meta.title`` is ``IN:<param>:<input_field>``;
in the bundled template that input holds the title itself as a placeholder.
"""

import copy
import json
from importlib import resources
from typing import Any

WORKFLOW_NAMES: tuple[str, ...] = (
    "txt2img",
    "remove_bg",
    "turnaround",
    "pose_grid",
    "pose_inpaint",
)

_PREFIX = "IN:"


class MissingBinding(ValueError):
    """A workflow parameter has no value, or a value matches no parameter."""


def load_workflow(name: str) -> dict:
    if name not in WORKFLOW_NAMES:
        raise ValueError(f"unknown workflow {name!r}")
    path = resources.files("pixelforge").joinpath("generation", "workflows", f"{name}.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _bindings(workflow: dict) -> dict[str, tuple[str, str]]:
    """Map each parameter name to (node_id, input_field)."""
    out: dict[str, tuple[str, str]] = {}
    for node_id, node in workflow.items():
        title = node.get("_meta", {}).get("title", "")
        if not title.startswith(_PREFIX):
            continue
        param, sep, field = title[len(_PREFIX) :].partition(":")
        if not param or not sep or not field:
            raise ValueError(f"malformed binding title {title!r} on node {node_id}")
        if param in out:
            raise ValueError(f"parameter {param!r} is bound on more than one node")
        out[param] = (node_id, field)
    return out


def params(workflow: dict) -> set[str]:
    return set(_bindings(workflow))


def required_nodes(workflow: dict) -> set[str]:
    return {node["class_type"] for node in workflow.values()}


def all_required_nodes() -> set[str]:
    """Node types needed by every bundled workflow."""
    return set().union(*(required_nodes(load_workflow(n)) for n in WORKFLOW_NAMES))


def bind(workflow: dict, values: dict[str, Any]) -> dict:
    """Return a deep copy of ``workflow`` with every ``IN:`` input set from ``values``."""
    bindings = _bindings(workflow)
    missing = sorted(set(bindings) - set(values))
    unknown = sorted(set(values) - set(bindings))
    if missing or unknown:
        parts = []
        if missing:
            parts.append(f"no value for {', '.join(missing)}")
        if unknown:
            parts.append(f"no node for {', '.join(unknown)}")
        raise MissingBinding("; ".join(parts))
    out = copy.deepcopy(workflow)
    for param, (node_id, field) in bindings.items():
        out[node_id]["inputs"][field] = copy.deepcopy(values[param])
    return out
