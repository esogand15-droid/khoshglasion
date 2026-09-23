"""Line diff for the lab and the archive. This does not publish anything."""
from __future__ import annotations

import difflib


def line_diff(original: str | None, formatted: str | None, limit: int = 40) -> list[dict]:
    rows: list[dict] = []
    for line in difflib.ndiff((original or "").splitlines(), (formatted or "").splitlines()):
        if line.startswith("+ "):
            kind = "add"
        elif line.startswith("- "):
            kind = "remove"
        elif line.startswith("? "):
            continue
        else:
            continue
        rows.append({"kind": kind, "text": line[2:]})
        if len(rows) >= limit:
            break
    return rows
