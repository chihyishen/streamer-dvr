from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from ...domain import SourceAuthMode


class RecordingPhase(str, Enum):
    SCHEDULED = "scheduled"
    PROBING = "probing"
    SOURCE_RESOLUTION = "source_resolution"
    RECORDING = "recording"
    CONVERTING = "converting"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class FailureCategory(str, Enum):
    PLATFORM_UNAVAILABLE = "platform_unavailable"
    SOURCE_UNSTABLE = "source_unstable"
    AUTH_INVALID = "auth_invalid"
    NETWORK_TRANSIENT = "network_transient"
    PROCESS_FAILURE = "process_failure"
    STATE_MACHINE_BUG = "state_machine_bug"
    FILESYSTEM_FAILURE = "filesystem_failure"
    DEPENDENCY_FAILURE = "dependency_failure"
    UNKNOWN = "unknown"


@dataclass
class ResolvedSource:
    session_id: str
    stream_url: str | None
    message: str
    room_status: str | None = None
    source_candidates: list[str] = field(default_factory=list)
    source_index: int = 0
    source_fingerprint: str | None = None
    validated_at: str | None = None
    resolver_tool: str | None = None
    auth_mode: SourceAuthMode = SourceAuthMode.UNKNOWN
    source_variant: str | None = None
    expires_at: str | None = None
    error_code: str | None = None
    failure_category: FailureCategory | None = None
    raw_output: str | None = None
    return_code: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class RecordingSession:
    id: str
    channel_id: str
    trigger: str
    started_at: str
    updated_at: str
    phase: RecordingPhase = RecordingPhase.SCHEDULED
    status: str = "active"
    message: str = ""
    active_pid: int | None = None
    source: ResolvedSource | None = None
    retry_count: int = 0
    failure_category: FailureCategory | None = None
    failure_phase: RecordingPhase | None = None
    failure_message: str | None = None
    ended_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
