from __future__ import annotations

from datetime import datetime, timedelta
from threading import RLock
from typing import Any
from uuid import uuid4

from ...common import utc_now_iso
from ...domain import (
    Event,
    RecordingSessionPhase as DomainRecordingSessionPhase,
    RecordingSessionStatus as DomainRecordingSessionStatus,
    SessionEvent as DomainSessionEvent,
)
from .classify import _normalize_text
from .mappers import (
    domain_failure_category,
    domain_phase,
    domain_status,
    to_domain_resolved_source,
    to_domain_session,
)
from .models import FailureCategory, RecordingPhase, RecordingSession, ResolvedSource


PROBE_NOISE_EVENT_TYPES = frozenset(
    {
        "recording_session_started",
        "recording_session_probing",
        "recording_session_source_resolution",
    }
)


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
        self.store.create_session(to_domain_session(session))
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
        self.store.link_session_resolved_source(session.id, to_domain_resolved_source(source))
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
            status=domain_status(session),
            current_phase=domain_phase(phase),
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
            status=domain_status(session),
            current_phase=domain_phase(session.phase),
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
            current_phase=domain_phase(phase),
            active_pid=None,
            ended_at=session.ended_at,
            final_failure_category=domain_failure_category(category),
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
                phase=domain_phase(session.phase),
                level=level,
                event_type=event_type,
                message=message,
                failure_category=domain_failure_category(session.failure_category),
                metadata=payload,
            )
        )

    def _should_suppress_global_event(self, event: Event) -> bool:
        if event.level.upper() != "ERROR":
            if self._is_probe_noise_event(event):
                return True
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

    def _is_probe_noise_event(self, event: Event) -> bool:
        metadata = event.metadata or {}
        if not isinstance(metadata, dict):
            metadata = {}
        if metadata.get("trigger") != "probe":
            return False
        if event.event_type in PROBE_NOISE_EVENT_TYPES:
            return True
        return event.event_type == "recording_session_completed" and metadata.get("outcome") == "aborted"
