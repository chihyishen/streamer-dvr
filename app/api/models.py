from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EventItem(BaseModel):
    timestamp: str
    timestamp_display: str | None = None
    level: str
    event_type: str
    channel_id: str | None = None
    channel_name: str | None = None
    session_id: str | None = None
    session_phase: str | None = None
    phase: str | None = None
    failure_category: str | None = None
    failure_message: str | None = None
    source_status: str | None = None
    source_url: str | None = None
    source_candidate_id: str | None = None
    source_path_tail: str | None = None
    session_status: str | None = None
    message: str
    summary: str | None = None
    tone: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelResponse(BaseModel):
    id: str
    username: str
    platform: str
    url: str
    category: str
    enabled: bool
    paused: bool
    poll_interval_seconds: int
    next_check_at: str | None = None
    max_resolution: int | None = None
    max_framerate: int | None = None
    filename_pattern: str
    created_at: int
    last_checked_at: str | None = None
    last_online_at: str | None = None
    last_recorded_file: str | None = None
    last_recorded_at: str | None = None
    last_error: str | None = None
    active_pid: int | None = None
    status: str
    status_label: str
    status_detail: str | None = None
    status_tone: str | None = None
    last_recorded_filename: str
    last_checked_display: str
    last_online_display: str
    last_recorded_display: str


class SessionSummary(BaseModel):
    id: str
    channel_id: str
    channel_name: str
    status: str
    phase: str
    is_active: bool
    started_at: str | None = None
    updated_at: str | None = None
    last_event_at: str | None = None
    summary: str
    failure_category: str | None = None
    failure_message: str | None = None
    source_status: str | None = None
    source_url: str | None = None
    source_candidate_id: str | None = None
    source_path_tail: str | None = None
    active_pid: int | None = None
    last_recorded_filename: str | None = None
    last_error: str | None = None
    event_count: int = 0


class SessionOverview(BaseModel):
    total_count: int = 0
    active_count: int = 0
    recent_count: int = 0
    source_issue_count: int = 0
    auth_issue_count: int = 0


class ChannelListResponse(BaseModel):
    items: list[ChannelResponse]


class DeleteResponse(BaseModel):
    ok: bool


class LogsResponse(BaseModel):
    items: list[EventItem]
    sessions: list[SessionSummary] = Field(default_factory=list)
    active_sessions: list[SessionSummary] = Field(default_factory=list)
    recent_sessions: list[SessionSummary] = Field(default_factory=list)
    session_overview: SessionOverview = Field(default_factory=SessionOverview)
    event_types: list[str]
    channels: list[dict[str, str]]
    total: int
    limit: int
    offset: int
    has_next: bool


class BootstrapResponse(BaseModel):
    channels: list[Any]
    sessions: list[SessionSummary] = Field(default_factory=list)
    active_sessions: list[SessionSummary] = Field(default_factory=list)
    recent_sessions: list[SessionSummary] = Field(default_factory=list)
    session_overview: SessionOverview = Field(default_factory=SessionOverview)
    categories: list[str]
    all_channels_count: int
    config: dict
    recent_events: list[EventItem]
