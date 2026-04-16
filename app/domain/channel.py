from __future__ import annotations

from pydantic import BaseModel

from .enums import Platform, Status


class Channel(BaseModel):
    id: str
    username: str
    platform: Platform = Platform.CHATURBATE
    url: str
    category: str = "default"
    enabled: bool = True
    paused: bool = False
    poll_interval_seconds: int = 300
    next_check_at: str | None = None
    max_resolution: int | None = None
    max_framerate: int | None = None
    filename_pattern: str = "{streamer}_{started_at}.{ext}"
    created_at: int
    last_checked_at: str | None = None
    last_online_at: str | None = None
    last_recorded_file: str | None = None
    last_recorded_at: str | None = None
    last_recording_duration_seconds: int | None = None
    status: Status = Status.IDLE
    last_error: str | None = None
    active_pid: int | None = None

    def is_active(self) -> bool:
        return self.enabled and not self.paused


class ChannelCreate(BaseModel):
    username: str
    platform: Platform = Platform.CHATURBATE
    url: str | None = None
    category: str = "default"
    enabled: bool = True
    paused: bool = False
    poll_interval_seconds: int | None = None
    max_resolution: int | None = None
    max_framerate: int | None = None
    filename_pattern: str | None = None


class ChannelUpdate(BaseModel):
    username: str | None = None
    platform: Platform | None = None
    url: str | None = None
    category: str | None = None
    enabled: bool | None = None
    paused: bool | None = None
    poll_interval_seconds: int | None = None
    max_resolution: int | None = None
    max_framerate: int | None = None
    filename_pattern: str | None = None
