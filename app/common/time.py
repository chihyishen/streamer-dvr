from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = ZoneInfo("Asia/Taipei")


def utc_now() -> datetime:
    return datetime.now(DEFAULT_TIMEZONE)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def format_display_time(value: str | None) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    return dt.astimezone(DEFAULT_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
