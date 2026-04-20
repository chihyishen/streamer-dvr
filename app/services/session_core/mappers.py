from __future__ import annotations

from ...domain import (
    FailureCategory as DomainFailureCategory,
    RecordingSession as DomainRecordingSession,
    RecordingSessionPhase as DomainRecordingSessionPhase,
    RecordingSessionStatus as DomainRecordingSessionStatus,
    ResolvedSource as DomainResolvedSource,
)
from .models import FailureCategory, RecordingPhase, RecordingSession, ResolvedSource


def domain_failure_category(category: FailureCategory | None) -> DomainFailureCategory | None:
    if category is None:
        return None
    return DomainFailureCategory(category.value)


def domain_phase(phase: RecordingPhase) -> DomainRecordingSessionPhase:
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


def domain_status(session: RecordingSession) -> DomainRecordingSessionStatus:
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


def to_domain_session(session: RecordingSession) -> DomainRecordingSession:
    return DomainRecordingSession(
        id=session.id,
        channel_id=session.channel_id,
        status=domain_status(session),
        current_phase=domain_phase(session.phase),
        created_at=session.started_at,
        updated_at=session.updated_at,
        started_at=session.started_at,
        ended_at=session.ended_at,
        active_pid=session.active_pid,
        final_failure_category=domain_failure_category(session.failure_category),
        final_failure_message=session.failure_message,
        metadata=dict(session.metadata),
    )


def to_domain_resolved_source(source: ResolvedSource) -> DomainResolvedSource:
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
