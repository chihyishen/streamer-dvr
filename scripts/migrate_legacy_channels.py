from __future__ import annotations

import json
import re
from pathlib import Path

from app.core import ROOT_DIR
from app.domain import Channel, Platform, Status


LEGACY_FILES = [
    ("channels.json", "channels"),
    ("channels 2.json", "channels-2"),
    ("channels 3.json", "channels-3"),
]


def slugify_category(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-") or "default"


def legacy_pattern_to_v2(_: str) -> str:
    return "{streamer}_{started_at}.{ext}"


def migrate_legacy_files(root: Path | None = None) -> list[Channel]:
    base = root or ROOT_DIR
    merged: dict[str, Channel] = {}

    for filename, fallback_category in LEGACY_FILES:
        path = base / filename
        if not path.exists():
            continue
        category = slugify_category(path.stem or fallback_category)
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload:
            username = item["username"].strip()
            if username in merged:
                continue
            paused = bool(item.get("is_paused", False))
            merged[username] = Channel(
                id=username,
                username=username,
                platform=Platform.CHATURBATE,
                url=f"https://chaturbate.com/{username}",
                category=category,
                enabled=True,
                paused=paused,
                poll_interval_seconds=300,
                next_check_at=None,
                max_resolution=None,
                max_framerate=None,
                filename_pattern=legacy_pattern_to_v2(item.get("pattern", "")),
                created_at=int(item.get("created_at", 0)),
                last_checked_at=None,
                last_online_at=None,
                last_recorded_file=None,
                last_recorded_at=None,
                status=Status.PAUSED if paused else Status.IDLE,
                last_error=None,
                active_pid=None,
            )

    return sorted(merged.values(), key=lambda channel: (channel.category, channel.username))


def write_migrated_channels(root: Path | None = None) -> int:
    base = root or ROOT_DIR
    channels = migrate_legacy_files(base)
    target = base / "channels.v2.json"
    target.write_text(
        json.dumps([channel.model_dump(mode="json") for channel in channels], indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return len(channels)


if __name__ == "__main__":
    count = write_migrated_channels()
    print(f"migrated {count} channels")
