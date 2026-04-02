from __future__ import annotations

from ..domain import RecordingSessionStatus


def build_session_filters(
    *,
    channel_id: str | None = None,
    status: str | None = None,
    phase: str | None = None,
    active_only: bool = False,
) -> tuple[str, list[object]]:
    conditions: list[str] = []
    values: list[object] = []
    if channel_id:
        conditions.append("channel_id = ?")
        values.append(channel_id)
    if status:
        conditions.append("status = ?")
        values.append(getattr(status, "value", status))
    if phase:
        conditions.append("current_phase = ?")
        values.append(getattr(phase, "value", phase))
    if active_only:
        active_statuses = sorted(RecordingSessionStatus.active_values())
        placeholders = ",".join("?" for _ in active_statuses)
        conditions.append(f"status IN ({placeholders})")
        values.extend(active_statuses)
        conditions.append("ended_at IS NULL")
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where_clause, values
