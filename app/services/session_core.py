from __future__ import annotations

from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Any
from uuid import uuid4

from ..common import utc_now_iso
from ..domain import (
    ErrorCode,
    Event,
    FailureCategory as DomainFailureCategory,
    RecordingSession as DomainRecordingSession,
    RecordingSessionPhase as DomainRecordingSessionPhase,
    RecordingSessionStatus as DomainRecordingSessionStatus,
    ResolvedSource as DomainResolvedSource,
    SessionEvent as DomainSessionEvent,
    SourceAuthMode,
)
from ..platform import RecordingFailure, StreamSourceResult


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


def _normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def _domain_failure_category(category: FailureCategory | None) -> DomainFailureCategory | None:
    if category is None:
        return None
    return DomainFailureCategory(category.value)


def _domain_phase(phase: RecordingPhase) -> DomainRecordingSessionPhase:
    mapping = {
        RecordingPhase.SCHEDULED: DomainRecordingSessionPhase.QUEUED,
        RecordingPhase.PROBING: DomainRecordingSessionPhase.PROBING,
        RecordingPhase.SOURCE_RESOLUTION: DomainRecordingSessionPhase.RESOLVING_SOURCE,
        RecordingPhase.RECORDING: DomainRecordingSessionPhase.RECORDING,
        RecordingPhase.CONVERTING: DomainRecordingSessionPhase.CONVERTING,
        RecordingPhase.RECOVERING: DomainRecordingSessionPhase.RECOVERING,
        RecordingPhase.COMPLETED: DomainRecordingSessionPhase.FINALIZING,
        RecordingPhase.FAILED: DomainRecordingSessionPhase.FINALIZING,
        RecordingPhase.ABORTED: DomainRecordingSessionPhase.ABORTED,
    }
    return mapping[phase]


def _domain_status(session: "RecordingSession") -> DomainRecordingSessionStatus:
    if session.status == "completed":
        return DomainRecordingSessionStatus.COMPLETED
    if session.status == "failed":
        return DomainRecordingSessionStatus.FAILED
    if session.status == "aborted":
        return DomainRecordingSessionStatus.ABORTED
    mapping = {
        RecordingPhase.SCHEDULED: DomainRecordingSessionStatus.QUEUED,
        RecordingPhase.PROBING: DomainRecordingSessionStatus.PROBING,
        RecordingPhase.SOURCE_RESOLUTION: DomainRecordingSessionStatus.RESOLVING_SOURCE,
        RecordingPhase.RECORDING: DomainRecordingSessionStatus.RECORDING,
        RecordingPhase.CONVERTING: DomainRecordingSessionStatus.CONVERTING,
        RecordingPhase.RECOVERING: DomainRecordingSessionStatus.RECOVERING,
        RecordingPhase.COMPLETED: DomainRecordingSessionStatus.COMPLETED,
        RecordingPhase.FAILED: DomainRecordingSessionStatus.FAILED,
        RecordingPhase.ABORTED: DomainRecordingSessionStatus.ABORTED,
    }
    return mapping[session.phase]


def classify_resolution_failure(result: StreamSourceResult) -> FailureCategory:
    metadata = result.metadata or {}
    room_status = _normalize_text(str(metadata.get("room_status") or ""))
    lowered = _normalize_text(result.message)
    error_code = result.error_code

    if room_status in {"offline", "not_online", "away", "private", "group_show", "hidden"}:
        return FailureCategory.PLATFORM_UNAVAILABLE
    if error_code == ErrorCode.AUTH_OR_COOKIE_FAILED or "cookie" in lowered or "auth" in lowered:
        return FailureCategory.AUTH_INVALID
    if error_code == ErrorCode.DEPENDENCY_MISSING:
        return FailureCategory.DEPENDENCY_FAILURE
    if error_code == ErrorCode.TIMEOUT or "timed out" in lowered or "deadline exceeded" in lowered:
        return FailureCategory.NETWORK_TRANSIENT
    if error_code in {
        ErrorCode.SOURCE_URL_EXPIRED,
        ErrorCode.SOURCE_RESOLVE_FAILED,
        ErrorCode.PAGE_FETCH_FAILED,
        ErrorCode.PLAYLIST_PARSE_FAILED,
    } and ("403" in lowered or "401" in lowered or "cookie" in lowered or "auth" in lowered or "rejected" in lowered):
        return FailureCategory.AUTH_INVALID
    if room_status == "public" and error_code in {
        ErrorCode.SOURCE_URL_EXPIRED,
        ErrorCode.SOURCE_RESOLVE_FAILED,
        ErrorCode.PAGE_FETCH_FAILED,
        ErrorCode.PLAYLIST_PARSE_FAILED,
    }:
        return FailureCategory.SOURCE_UNSTABLE
    if error_code in {
        ErrorCode.SOURCE_URL_EXPIRED,
        ErrorCode.SOURCE_RESOLVE_FAILED,
        ErrorCode.PAGE_FETCH_FAILED,
        ErrorCode.PLAYLIST_PARSE_FAILED,
    }:
        if "404" in lowered or "m3u8" in lowered or "playlist" in lowered or "parse" in lowered:
            return FailureCategory.SOURCE_UNSTABLE
        return FailureCategory.NETWORK_TRANSIENT
    if "offline" in lowered or "private" in lowered or "hidden" in lowered:
        return FailureCategory.PLATFORM_UNAVAILABLE
    return FailureCategory.UNKNOWN


def classify_recording_failure(failure: RecordingFailure, *, room_status: str | None = None) -> FailureCategory:
    lowered = _normalize_text(failure.message)
    normalized_room_status = _normalize_text(room_status)
    error_code = failure.error_code

    if normalized_room_status in {"offline", "not_online", "away", "private", "group_show", "hidden"}:
        return FailureCategory.PLATFORM_UNAVAILABLE
    if error_code == ErrorCode.DEPENDENCY_MISSING:
        return FailureCategory.DEPENDENCY_FAILURE
    if error_code == ErrorCode.CONVERT_FAILED:
        return FailureCategory.PROCESS_FAILURE
    if error_code == ErrorCode.AUTH_OR_COOKIE_FAILED or "auth" in lowered or "cookie" in lowered:
        return FailureCategory.AUTH_INVALID
    if error_code in {
        ErrorCode.SOURCE_URL_EXPIRED,
        ErrorCode.SOURCE_RESOLVE_FAILED,
        ErrorCode.PLAYLIST_PARSE_FAILED,
    } and ("403" in lowered or "401" in lowered or "cookie" in lowered or "auth" in lowered or "rejected" in lowered):
        return FailureCategory.AUTH_INVALID
    if error_code == ErrorCode.TIMEOUT or "timed out" in lowered or "deadline exceeded" in lowered:
        return FailureCategory.NETWORK_TRANSIENT
    if error_code in {
        ErrorCode.SOURCE_URL_EXPIRED,
        ErrorCode.SOURCE_RESOLVE_FAILED,
        ErrorCode.PLAYLIST_PARSE_FAILED,
    }:
        return FailureCategory.SOURCE_UNSTABLE
    if error_code == ErrorCode.RECORDER_EXITED:
        if "404" in lowered or "playlist" in lowered or "m3u8" in lowered:
            return FailureCategory.SOURCE_UNSTABLE
        if "private" in lowered or "hidden" in lowered or "away" in lowered:
            return FailureCategory.PLATFORM_UNAVAILABLE
        return FailureCategory.PROCESS_FAILURE
    return FailureCategory.UNKNOWN


class RecordingSessionRegistry:
    ERROR_DEDUP_WINDOW = timedelta(minutes=20)

    def __init__(self, store) -> None:
        self.store = store
        self._lock = RLock()
        self._by_channel: dict[str, RecordingSession] = {}
        self._by_id: dict[str, RecordingSession] = {}

    def open(self, channel_id: str, *, trigger: str, metadata: dict[str, Any] | None = None) -> RecordingSession:
        session = RecordingSession(
            id=uuid4().hex,
            channel_id=channel_id,
            trigger=trigger,
            started_at=utc_now_iso(),
            updated_at=utc_now_iso(),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._by_channel[channel_id] = session
            self._by_id[session.id] = session
        self.store.create_session(self._domain_session(session))
        self._emit(session, level="INFO", event_type="recording_session_started", message=f"Session started from {trigger}", phase=session.phase.value)
        return session

    def get(self, channel_id: str) -> RecordingSession | None:
        with self._lock:
            return self._by_channel.get(channel_id)

    def get_by_id(self, session_id: str) -> RecordingSession | None:
        with self._lock:
            return self._by_id.get(session_id)

    def active_sessions(self) -> list[RecordingSession]:
        with self._lock:
            return list(self._by_id.values())

    def attach_source(self, session: RecordingSession, source: ResolvedSource) -> None:
        session.source = source
        session.updated_at = utc_now_iso()
        session.metadata.update(source.metadata)
        session.metadata["session_id"] = session.id
        session.metadata["source_fingerprint"] = source.source_fingerprint
        session.metadata["source_url"] = source.stream_url
        session.metadata["room_status"] = source.room_status
        session.metadata["source_candidates"] = source.source_candidates
        session.metadata["source_index"] = source.source_index
        self.store.link_session_resolved_source(session.id, self._domain_resolved_source(source))
        self._emit(
            session,
            level="INFO",
            event_type="recording_session_source_acquired",
            message=source.message,
            phase=RecordingPhase.SOURCE_RESOLUTION.value,
            room_status=source.room_status,
            source_fingerprint=source.source_fingerprint,
            source_url=source.stream_url,
            source_index=source.source_index,
            failure_category=(source.failure_category.value if source.failure_category else None),
            raw_output=source.raw_output,
            return_code=source.return_code,
        )

    def transition(
        self,
        session: RecordingSession,
        phase: RecordingPhase,
        message: str,
        *,
        event_type: str,
        level: str = "INFO",
        **metadata: Any,
    ) -> None:
        session.phase = phase
        session.message = message
        session.updated_at = utc_now_iso()
        session.metadata.update(metadata)
        self.store.update_session(
            session.id,
            status=_domain_status(session),
            current_phase=_domain_phase(phase),
            active_pid=session.active_pid,
            metadata=dict(session.metadata),
        )
        self._emit(session, level=level, event_type=event_type, message=message, phase=phase.value, **metadata)

    def mark_recording(self, session: RecordingSession, *, active_pid: int | None = None, source_path: str | None = None) -> None:
        session.phase = RecordingPhase.RECORDING
        session.active_pid = active_pid
        session.updated_at = utc_now_iso()
        if source_path:
            session.metadata["source_path"] = source_path
        self.store.update_session(
            session.id,
            status=DomainRecordingSessionStatus.RECORDING,
            current_phase=DomainRecordingSessionPhase.RECORDING,
            active_pid=active_pid,
            started_at=session.started_at,
            metadata=dict(session.metadata),
        )
        self._emit(
            session,
            level="INFO",
            event_type="recording_session_recording",
            message="Recording started",
            phase=RecordingPhase.RECORDING.value,
            active_pid=active_pid,
            source_path=source_path,
        )

    def complete(self, session: RecordingSession, *, message: str, outcome: str = "completed", **metadata: Any) -> None:
        session.phase = RecordingPhase.COMPLETED if outcome == "completed" else RecordingPhase.ABORTED
        session.status = outcome
        session.ended_at = utc_now_iso()
        session.updated_at = session.ended_at
        session.metadata.update(metadata)
        self.store.update_session(
            session.id,
            status=_domain_status(session),
            current_phase=_domain_phase(session.phase),
            active_pid=None,
            ended_at=session.ended_at,
            metadata=dict(session.metadata),
        )
        self._emit(
            session,
            level="INFO",
            event_type="recording_session_completed",
            message=message,
            phase=session.phase.value,
            outcome=outcome,
            **metadata,
        )
        self._close(session)

    def fail(
        self,
        session: RecordingSession,
        *,
        phase: RecordingPhase,
        category: FailureCategory,
        message: str,
        event_type: str = "recording_session_failed",
        **metadata: Any,
    ) -> None:
        session.phase = RecordingPhase.FAILED
        session.failure_phase = phase
        session.failure_category = category
        session.failure_message = message
        session.status = "failed"
        session.ended_at = utc_now_iso()
        session.updated_at = session.ended_at
        session.metadata.update(metadata)
        self.store.update_session(
            session.id,
            status=DomainRecordingSessionStatus.FAILED,
            current_phase=_domain_phase(phase),
            active_pid=None,
            ended_at=session.ended_at,
            final_failure_category=_domain_failure_category(category),
            final_failure_message=message,
            metadata=dict(session.metadata),
        )
        self._emit(
            session,
            level="ERROR",
            event_type=event_type,
            message=message,
            phase=phase.value,
            failure_category=category.value,
            **metadata,
        )
        self._close(session)

    def _close(self, session: RecordingSession) -> None:
        with self._lock:
            current = self._by_channel.get(session.channel_id)
            if current and current.id == session.id:
                self._by_channel.pop(session.channel_id, None)

    def _emit(self, session: RecordingSession, *, level: str, event_type: str, message: str, **metadata: Any) -> None:
        payload = {
            "session_id": session.id,
            "channel_id": session.channel_id,
            "trigger": session.trigger,
            "phase": metadata.pop("phase", session.phase.value),
            "status": session.status,
            "started_at": session.started_at,
            "updated_at": session.updated_at,
            **session.metadata,
            **metadata,
        }
        event = Event(
            timestamp=utc_now_iso(),
            level=level,
            event_type=event_type,
            channel_id=session.channel_id,
            message=message,
            metadata=payload,
        )
        if not self._should_suppress_global_event(event):
            self.store.append_event(event)
        self.store.append_session_event(
            DomainSessionEvent(
                session_id=session.id,
                timestamp=utc_now_iso(),
                phase=_domain_phase(session.phase),
                level=level,
                event_type=event_type,
                message=message,
                failure_category=_domain_failure_category(session.failure_category),
                metadata=payload,
            )
        )

    def _should_suppress_global_event(self, event: Event) -> bool:
        if event.level.upper() != "ERROR":
            return False
        try:
            recent = self.store.read_events(limit=20, channel_id=event.channel_id, level="ERROR")
        except Exception:
            return False
        event_category = _normalize_text((event.metadata or {}).get("failure_category"))
        event_message = _normalize_text(event.message)
        event_time = datetime.fromisoformat(event.timestamp)
        for item in recent:
            item_message = _normalize_text(item.get("message"))
            if item_message != event_message:
                continue
            metadata = item.get("metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {}
            item_category = _normalize_text(metadata.get("failure_category"))
            if item_category != event_category:
                continue
            timestamp = item.get("timestamp")
            if not isinstance(timestamp, str):
                continue
            try:
                item_time = datetime.fromisoformat(timestamp)
            except ValueError:
                continue
            if event_time - item_time <= self.ERROR_DEDUP_WINDOW:
                return True
        return False

    def _domain_session(self, session: RecordingSession) -> DomainRecordingSession:
        return DomainRecordingSession(
            id=session.id,
            channel_id=session.channel_id,
            status=_domain_status(session),
            current_phase=_domain_phase(session.phase),
            created_at=session.started_at,
            updated_at=session.updated_at,
            started_at=session.started_at,
            ended_at=session.ended_at,
            active_pid=session.active_pid,
            final_failure_category=_domain_failure_category(session.failure_category),
            final_failure_message=session.failure_message,
            metadata=dict(session.metadata),
        )

    def _domain_resolved_source(self, source: ResolvedSource) -> DomainResolvedSource:
        return DomainResolvedSource(
            id=source.id,
            session_id=source.session_id,
            resolver_tool=source.resolver_tool or "runtime",
            candidate_index=source.source_index,
            candidate_url=source.source_candidates[source.source_index] if source.source_candidates else source.stream_url,
            stream_url=source.stream_url,
            room_status=source.room_status,
            auth_mode=source.auth_mode,
            source_variant=source.source_variant,
            source_fingerprint=source.source_fingerprint,
            validated_at=source.validated_at,
            expires_at=source.expires_at,
            message=source.message,
            raw_output=source.raw_output,
            return_code=source.return_code,
            metadata=dict(source.metadata),
        )
