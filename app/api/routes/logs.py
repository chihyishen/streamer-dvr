from __future__ import annotations

from fastapi import FastAPI, Query

from ...services import ChannelService
from ...storage import JsonStore
from ..models import LogsResponse
from ..serializers import channel_name_map, serialize_event, serialize_logs_response


def register_log_routes(app: FastAPI, *, store: JsonStore, channel_service: ChannelService) -> None:
    @app.get("/api/logs", response_model=LogsResponse)
    async def api_logs(
        channel_id: str | None = None,
        event_type: str | None = None,
        level: str | None = None,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=300, ge=20, le=1000),
    ):
        channels = channel_service.list_channels()
        channel_name_by_id = channel_name_map(channels)
        events = store.read_events(
            limit=limit,
            offset=offset,
            channel_id=channel_id or None,
            event_type=event_type or None,
            level=level or None,
        )
        total = store.count_events(
            channel_id=channel_id or None,
            event_type=event_type or None,
            level=level or None,
        )
        event_samples = store.read_recent_events(800)
        event_types = sorted({event.get("event_type", "") for event in event_samples if event.get("event_type")})
        items = [serialize_event(event, channel_name_by_id) for event in events]
        has_next = total > (offset + limit)
        return serialize_logs_response(
            channels,
            items,
            event_types,
            total=total,
            limit=limit,
            offset=offset,
            has_next=has_next,
            recent_events=event_samples,
        )
