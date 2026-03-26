from __future__ import annotations
from typing import Any
from pathlib import Path
from ..domain import Channel, Event, AppConfig
from ..common.time import format_display_time
from ..common.ui import display_status, display_filename
from ..common.events import summarize_event, event_tone

def serialize_channel(channel: Any) -> dict:
    if hasattr(channel, "model_dump"):
        data = channel.model_dump(mode="json")
    else:
        data = dict(channel)
    
    status_val = data.get("status", "idle")
    data["status_label"] = display_status(status_val)
    
    last_file = data.get("last_recorded_file")
    data["last_recorded_filename"] = Path(last_file).name if last_file else "-"
    
    data["last_checked_display"] = format_display_time(data.get("last_checked_at"))
    data["last_online_display"] = format_display_time(data.get("last_online_at"))
    data["last_recorded_display"] = format_display_time(data.get("last_recorded_at"))
    
    return data

def channel_name_map(channels: list[Any]) -> dict[str, str]:
    mapping = {}
    for c in channels:
        if hasattr(c, "id"):
            mapping[c.id] = getattr(c, "username", c.id)
        elif isinstance(c, dict):
            mapping[c["id"]] = c.get("username", c["id"])
    return mapping

def serialize_event(event: Any, channel_names: dict[str, str] | None = None) -> dict:
    if hasattr(event, "model_dump"):
        data = event.model_dump(mode="json")
    else:
        data = dict(event)
            
    etype = data.get("event_type", "")
    msg = data.get("message", "")
    
    data["summary"] = summarize_event(etype, msg)
    data["tone"] = event_tone(etype, msg)
    data["timestamp_display"] = format_display_time(data.get("timestamp"))
    
    cid = data.get("channel_id")
    if channel_names and cid in channel_names:
        data["channel_name"] = channel_names[cid]
    else:
        data["channel_name"] = data.get("channel_id") or "-"
        
    return data

def serialize_logs_response(channels, items, event_types, total, limit, offset, has_next=True):
    # 此處的 items 可能是已經 serialize_event 過的，也可能沒
    names = channel_name_map(channels)
    return {
        "items": [serialize_event(i, names) for i in items],
        "event_types": event_types,
        "channels": [{"id": k, "username": v} for k, v in names.items()],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_next": has_next
    }

def serialize_bootstrap(channels, config_dict, events):
    names = channel_name_map(channels)
    categories = []
    for c in channels:
        cat = getattr(c, "category", None) or (c.get("category") if isinstance(c, dict) else "default")
        if cat not in categories:
            categories.append(cat)
    
    return {
        "channels": [serialize_channel(c) for c in channels],
        "categories": sorted(categories),
        "all_channels_count": len(channels),
        "config": config_dict,
        "recent_events": [serialize_event(e, names) for e in events]
    }
