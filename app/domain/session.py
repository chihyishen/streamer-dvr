from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .enums import FailureCategory, RecordingSessionPhase, RecordingSessionStatus, SourceAuthMode


class ResolvedSource(BaseModel):
    id: str
    session_id: str
    resolver_tool: str
    candidate_index: int = 0
    candidate_url: str | None = None
    stream_url: str | None = None
    room_status: str | None = None
    auth_mode: SourceAuthMode = SourceAuthMode.UNKNOWN
    source_variant: str | None = None
    source_fingerprint: str | None = None
    validated_at: str | None = None
    expires_at: str | None = None
    message: str | None = None
    raw_output: str | None = None
    return_code: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecordingSession(BaseModel):
    id: str
    channel_id: str
    status: RecordingSessionStatus = RecordingSessionStatus.QUEUED
    current_phase: RecordingSessionPhase = RecordingSessionPhase.QUEUED
    created_at: str
    updated_at: str
    started_at: str | None = None
    ended_at: str | None = None
    last_heartbeat_at: str | None = None
    active_pid: int | None = None
    active_resolved_source_id: str | None = None
    final_failure_category: FailureCategory | None = None
    final_failure_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    active_resolved_source: ResolvedSource | None = None


class RecordingSessionUpdate(BaseModel):
    status: RecordingSessionStatus | None = None
    current_phase: RecordingSessionPhase | None = None
    updated_at: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    last_heartbeat_at: str | None = None
    active_pid: int | None = None
    active_resolved_source_id: str | None = None
    final_failure_category: FailureCategory | None = None
    final_failure_message: str | None = None
    metadata: dict[str, Any] | None = None


class SessionEvent(BaseModel):
    id: int | None = None
    session_id: str
    timestamp: str
    phase: RecordingSessionPhase
    level: str
    event_type: str
    message: str
    failure_category: FailureCategory | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
