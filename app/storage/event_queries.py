from __future__ import annotations


def build_event_filters(
    *,
    channel_id: str | None = None,
    event_type: str | None = None,
    level: str | None = None,
) -> tuple[str, list[object]]:
    conditions: list[str] = []
    values: list[object] = []
    if channel_id:
        conditions.append("channel_id = ?")
        values.append(channel_id)
    if event_type:
        conditions.append("event_type = ?")
        values.append(event_type)
    if level:
        conditions.append("UPPER(level) = ?")
        values.append(level.upper())
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where_clause, values
