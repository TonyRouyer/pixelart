"""Small text helpers shared across modules."""

from __future__ import annotations

import re
import unicodedata


def slugify(name: str) -> str:
    """ASCII, lowercase, dash-separated slug; falls back to "project" when empty."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "project"
