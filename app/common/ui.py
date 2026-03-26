from __future__ import annotations

from pathlib import Path


def display_status(value: str) -> str:
    mapping = {
        "idle": "offline",
        "checking": "offline",
        "recording": "recording",
        "paused": "paused",
        "error": "error",
    }
    return mapping.get(value, value)


def display_filename(value: str | None) -> str:
    if not value:
        return "No recordings yet"
    return Path(value).name
