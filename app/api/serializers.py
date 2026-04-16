from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ..common.events import event_tone, summarize_event
from ..common.time import format_display_time
from ..common.ui import display_status

SOURCE_FAILURE_CATEGORIES = {
    "source_unstable",
    "source_resolve_failed",
    "source_url_expired",
    "playlist_parse_failed",
}

AUTH_FAILURE_CATEGORIES = {
    "auth_invalid",
    "auth_or_cookie_failed",
}

DISPLAY_EVENT_LEVELS = {"ERROR"}

EVENT_FAILURE_CATEGORY_MAP = {
    "AUTH_OR_COOKIE_FAILED": "auth_invalid",
    "DEPENDENCY_MISSING": "dependency_failure",
    "PAGE_FETCH_FAILED": "source_unstable",
    "PLAYLIST_PARSE_FAILED": "source_unstable",
    "RECORDER_EXITED": "process_failure",
    "SOURCE_RESOLVE_FAILED": "source_unstable",
    "SOURCE_URL_EXPIRED": "source_unstable",
    "TIMEOUT": "network_transient",
    "VALIDATION_FAILED": "state_machine_bug",
}

EVENT_PHASE_MAP = {
    "convert_completed": "completed",
    "recording_completed": "converting",
    "recording_started": "recording",
    "recording_stopped": "idle",
    "recording_stop_requested": "stopping",
    "source_candidate_retry": "source_refresh",
    "source_refresh_retry": "source_refresh",
    "stream_online": "recording",
    "stream_unavailable": "idle",
}


def _payload_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    return dict(item)


def _metadata_from(data: dict[str, Any]) -> dict[str, Any]:
    metadata = data.get("metadata") or {}
    if isinstance(metadata, dict):
        return dict(metadata)
    return {}


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _latest_events_by_channel(events: list[Any]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for event in events:
        data = _payload_dict(event)
        channel_id = _string_or_none(data.get("channel_id"))
        if not channel_id or channel_id in latest:
            continue
        latest[channel_id] = data
    return latest


def _infer_failure_category(event_type: str, message: str, metadata: dict[str, Any]) -> str | None:
    explicit = _string_or_none(metadata.get("failure_category"))
    if explicit:
        return explicit
    mapped = EVENT_FAILURE_CATEGORY_MAP.get(event_type)
    if mapped:
        return mapped
    lowered = message.lower()
    if "cookie" in lowered or "auth" in lowered:
        return "auth_invalid"
    if "source" in lowered or "playlist" in lowered or "m3u8" in lowered or "404" in lowered:
        return "source_unstable"
    if "timeout" in lowered or "timed out" in lowered:
        return "network_transient"
    if "stalled" in lowered or "exited" in lowered or "process" in lowered:
        return "process_failure"
    return None


def _infer_phase(event_type: str, channel_status: str, metadata: dict[str, Any]) -> str:
    explicit = _string_or_none(metadata.get("phase") or metadata.get("session_phase"))
    if explicit:
        return explicit
    mapped = EVENT_PHASE_MAP.get(event_type)
    if mapped:
        return mapped
    lowered = channel_status.lower()
    if lowered == "recording":
        return "recording"
    if lowered == "paused":
        return "paused"
    if lowered == "error":
        return "failed"
    return "idle"


def _infer_session_status(channel_status: str, metadata: dict[str, Any]) -> str:
    explicit = _string_or_none(metadata.get("session_status"))
    if explicit:
        return explicit
    lowered = channel_status.lower()
    if lowered in {"recording", "checking"}:
        return lowered
    if lowered == "error":
        return "failed"
    if lowered == "paused":
        return "paused"
    return "idle"


def _is_active_session(channel_status: str, active_pid: Any, metadata: dict[str, Any]) -> bool:
    explicit = metadata.get("is_active")
    if isinstance(explicit, bool):
        return explicit
    return bool(active_pid) or channel_status.lower() == "recording"


def _build_session_snapshot(
    channel: dict[str, Any],
    latest_event: dict[str, Any] | None,
    channel_names: dict[str, str],
    event_count: int,
) -> dict[str, Any]:
    metadata = _metadata_from(latest_event) if latest_event else {}
    channel_id = _string_or_none(channel.get("id")) or "-"
    channel_name = channel_names.get(channel_id, _string_or_none(channel.get("username")) or channel_id)
    channel_status = _string_or_none(channel.get("status")) or "idle"
    event_type = _string_or_none(latest_event.get("event_type")) if latest_event else ""
    message = _string_or_none(latest_event.get("message")) if latest_event else None
    summary = _string_or_none(latest_event.get("summary")) if latest_event else None
    event_timestamp = _string_or_none(latest_event.get("timestamp")) if latest_event else None
    failure_category = _infer_failure_category(event_type or "", message or channel_status, metadata)
    session_id = (
        _string_or_none(metadata.get("session_id"))
        or _string_or_none(metadata.get("recording_session_id"))
        or _string_or_none(latest_event.get("session_id") if latest_event else None)
        or f"{channel_id}:{_string_or_none(channel.get('active_pid')) or _string_or_none(channel.get('last_recorded_at')) or channel_status}"
    )
    phase = _infer_phase(event_type or "", channel_status, metadata)
    session_status = _infer_session_status(channel_status, metadata)
    is_active = _is_active_session(channel_status, channel.get("active_pid"), metadata)
    started_at = (
        _string_or_none(metadata.get("started_at"))
        or _string_or_none(metadata.get("session_started_at"))
        or (_string_or_none(latest_event.get("timestamp")) if latest_event and event_type == "recording_started" else None)
        or _string_or_none(channel.get("last_recorded_at"))
        or _string_or_none(channel.get("last_online_at"))
    )
    updated_at = (
        _string_or_none(metadata.get("updated_at"))
        or _string_or_none(metadata.get("session_updated_at"))
        or event_timestamp
        or _string_or_none(channel.get("last_checked_at"))
    )
    source_status = _string_or_none(metadata.get("source_status") or metadata.get("room_status"))
    source_url = _string_or_none(metadata.get("source_url") or metadata.get("resolved_source"))
    source_candidate_id = _string_or_none(metadata.get("source_candidate_id") or metadata.get("candidate_id"))
    source_path_tail = _string_or_none(metadata.get("source_path_tail"))
    failure_message = _string_or_none(metadata.get("failure_message")) or _string_or_none(channel.get("last_error"))
    if not failure_message and failure_category and message:
        failure_message = message

    last_recorded_file = _string_or_none(channel.get("last_recorded_file"))
    last_recorded_filename = _string_or_none(channel.get("last_recorded_filename"))
    if not last_recorded_filename and last_recorded_file:
        last_recorded_filename = Path(last_recorded_file).name

    return {
        "id": session_id,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "status": session_status,
        "phase": phase,
        "is_active": is_active,
        "started_at": started_at,
        "updated_at": updated_at,
        "last_event_at": event_timestamp,
        "summary": summary or failure_message or display_status(channel_status),
        "failure_category": failure_category,
        "failure_message": failure_message,
        "source_status": source_status,
        "source_url": source_url,
        "source_candidate_id": source_candidate_id,
        "source_path_tail": source_path_tail,
        "active_pid": channel.get("active_pid"),
        "last_recorded_filename": last_recorded_filename,
        "last_error": _string_or_none(channel.get("last_error")),
        "event_count": event_count,
    }


def _sort_session_snapshot(session: dict[str, Any]) -> tuple[int, str, str]:
    updated_at = _string_or_none(session.get("updated_at")) or ""
    channel_name = _string_or_none(session.get("channel_name")) or ""
    return (0 if session.get("is_active") else 1, updated_at, channel_name.lower())


def _channel_status_from_event(channel: dict[str, Any], event: dict[str, Any] | None) -> tuple[str, str]:
    status = (_string_or_none(channel.get("status")) or "idle").lower()
    last_error = _string_or_none(channel.get("last_error"))
    message = _string_or_none(event.get("message")) if event else None
    summary = _string_or_none(event.get("summary")) if event else None
    combined = " ".join(part for part in [summary, message, last_error] if part).lower()

    if status == "recording":
        return "Online", "good"
    if status == "paused":
        return "Paused", "neutral"
    if "password protected" in combined or "requires a password" in combined:
        return "Password protected", "neutral"
    if "private show" in combined or "private session" in combined:
        return "Private show", "neutral"
    if "hidden show" in combined or "hidden session" in combined or "secret show" in combined or "ticket show" in combined or "hidden cam" in combined:
        return "Hidden show", "neutral"
    if "source unstable" in combined or "source resolve failed" in combined or "404" in combined or "playlist parse failed" in combined:
        return "Source unstable", "bad"
    if "auth" in combined or "cookie" in combined:
        return "Auth issue", "bad"
    if "offline" in combined or "away" in combined:
        return "Offline", "neutral"
    if status == "error":
        return "Error", "bad"
    return "Offline", "neutral"


def _decorate_channels_with_status(channels: list[dict[str, Any]], events: list[Any]) -> list[dict[str, Any]]:
    latest_events = _latest_events_by_channel(events)
    for channel in channels:
        channel_id = _string_or_none(channel.get("id")) or ""
        latest_event = latest_events.get(channel_id)
        detail, tone = _channel_status_from_event(channel, latest_event)
        channel["status_detail"] = detail
        channel["status_tone"] = tone
    return channels


def _is_displayable_event(event: Any) -> bool:
    data = _payload_dict(event)
    level = (_string_or_none(data.get("level")) or "").upper()
    return level in DISPLAY_EVENT_LEVELS


def _is_meaningful_session(session: dict[str, Any]) -> bool:
    status = (_string_or_none(session.get("status")) or "").lower()
    phase = (_string_or_none(session.get("phase")) or "").lower()
    failure_category = _string_or_none(session.get("failure_category"))
    last_error = _string_or_none(session.get("last_error"))
    return bool(
        session.get("is_active")
        or failure_category
        or last_error
        or status in {"failed", "recording", "converting", "recovering", "stalled"}
        or phase in {"recording", "converting", "recovering", "failed"}
    )


def build_session_summaries(channels: list[Any], events: list[Any]) -> list[dict[str, Any]]:
    names = channel_name_map(channels)
    latest_events = _latest_events_by_channel(events)
    event_counts: Counter[str] = Counter()
    for event in events:
        data = _payload_dict(event)
        channel_id = _string_or_none(data.get("channel_id"))
        if channel_id:
            event_counts[channel_id] += 1
    sessions: list[dict[str, Any]] = []
    for channel in channels:
        channel_data = _payload_dict(channel)
        channel_id = _string_or_none(channel_data.get("id")) or ""
        sessions.append(
            _build_session_snapshot(
                channel_data,
                latest_events.get(channel_id),
                names,
                event_counts.get(channel_id, 0),
            )
        )
    sessions.sort(key=_sort_session_snapshot)
    return sessions


def build_session_overview(sessions: list[dict[str, Any]], recent_session_limit: int) -> dict[str, int]:
    active_count = sum(1 for session in sessions if session.get("is_active"))
    source_issue_count = sum(1 for session in sessions if session.get("failure_category") in SOURCE_FAILURE_CATEGORIES or session.get("source_status") in {"error", "failed"})
    auth_issue_count = sum(1 for session in sessions if session.get("failure_category") in AUTH_FAILURE_CATEGORIES)
    return {
        "total_count": len(sessions),
        "active_count": active_count,
        "recent_count": min(len(sessions), recent_session_limit),
        "source_issue_count": source_issue_count,
        "auth_issue_count": auth_issue_count,
    }


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes > 0:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def serialize_channel(channel: Any) -> dict:
    data = _payload_dict(channel)
    status_val = data.get("status", "idle")
    data["status_label"] = display_status(status_val)
    last_file = data.get("last_recorded_file")
    data["last_recorded_filename"] = Path(last_file).name if last_file else "-"
    data["last_checked_display"] = format_display_time(data.get("last_checked_at"))
    data["last_online_display"] = format_display_time(data.get("last_online_at"))
    data["last_recorded_display"] = format_display_time(data.get("last_recorded_at"))
    data["last_recording_duration_display"] = _format_duration(data.get("last_recording_duration_seconds"))
    return data


def channel_name_map(channels: list[Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for channel in channels:
        data = _payload_dict(channel)
        channel_id = _string_or_none(data.get("id"))
        if not channel_id:
            continue
        mapping[channel_id] = _string_or_none(data.get("username")) or channel_id
    return mapping


def serialize_event(event: Any, channel_names: dict[str, str] | None = None) -> dict:
    data = _payload_dict(event)
    metadata = _metadata_from(data)
    event_type = _string_or_none(data.get("event_type")) or ""
    message = _string_or_none(data.get("message")) or ""

    data["summary"] = summarize_event(event_type, message)
    data["tone"] = event_tone(event_type, message)
    data["timestamp_display"] = format_display_time(data.get("timestamp"))

    cid = _string_or_none(data.get("channel_id"))
    if channel_names and cid in channel_names:
        data["channel_name"] = channel_names[cid]
    else:
        data["channel_name"] = cid or "-"

    data["session_id"] = _string_or_none(metadata.get("session_id") or metadata.get("recording_session_id") or data.get("session_id"))
    data["session_phase"] = _string_or_none(metadata.get("session_phase") or metadata.get("phase") or EVENT_PHASE_MAP.get(event_type))
    data["phase"] = data["session_phase"]
    data["failure_category"] = _infer_failure_category(event_type, message, metadata)
    data["failure_message"] = _string_or_none(metadata.get("failure_message")) or (_string_or_none(message) if data["failure_category"] else None)
    data["session_status"] = _string_or_none(metadata.get("session_status") or data["session_phase"])
    data["source_status"] = _string_or_none(metadata.get("source_status") or metadata.get("room_status"))
    data["source_url"] = _string_or_none(metadata.get("source_url") or metadata.get("resolved_source"))
    data["source_candidate_id"] = _string_or_none(metadata.get("source_candidate_id") or metadata.get("candidate_id"))
    data["source_path_tail"] = _string_or_none(metadata.get("source_path_tail"))
    return data


def serialize_logs_response(
    channels: list[Any],
    items: list[Any],
    event_types: list[str],
    total: int,
    limit: int,
    offset: int,
    has_next: bool = True,
    recent_events: list[Any] | None = None,
) -> dict[str, Any]:
    names = channel_name_map(channels)
    session_events = recent_events if recent_events is not None else items
    sessions = build_session_summaries(channels, session_events)
    active_sessions = [session for session in sessions if session["is_active"]]
    recent_sessions = [session for session in sessions if _is_meaningful_session(session)][:8]
    session_overview = build_session_overview(sessions, len(recent_sessions))
    return {
        "items": [serialize_event(item, names) for item in items],
        "sessions": sessions,
        "active_sessions": active_sessions,
        "recent_sessions": recent_sessions,
        "session_overview": session_overview,
        "event_types": event_types,
        "channels": [{"id": channel_id, "username": username} for channel_id, username in names.items()],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_next": has_next,
    }


def serialize_bootstrap(channels: list[Any], config_dict: dict, events: list[Any]) -> dict[str, Any]:
    names = channel_name_map(channels)
    categories: list[str] = []
    serialized_channels = _decorate_channels_with_status([serialize_channel(channel) for channel in channels], events)
    for channel in serialized_channels:
        category = _string_or_none(channel.get("category")) or "default"
        if category not in categories:
            categories.append(category)

    sessions = build_session_summaries(serialized_channels, events)
    active_sessions = [session for session in sessions if session["is_active"]]
    recent_sessions = [session for session in sessions if _is_meaningful_session(session)][:8]
    session_overview = build_session_overview(sessions, len(recent_sessions))
    recent_events = [serialize_event(event, names) for event in events if _is_displayable_event(event)]

    return {
        "channels": serialized_channels,
        "sessions": sessions,
        "active_sessions": active_sessions,
        "recent_sessions": recent_sessions,
        "session_overview": session_overview,
        "categories": sorted(categories),
        "all_channels_count": len(serialized_channels),
        "config": config_dict,
        "recent_events": recent_events,
    }
