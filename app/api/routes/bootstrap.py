from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from ...services import ChannelService
from ...storage import JsonStore
from ..models import BootstrapResponse
from ..serializers import channel_name_map, serialize_bootstrap, serialize_event


def register_bootstrap_routes(app: FastAPI, *, store: JsonStore, channel_service: ChannelService) -> None:
    @app.get("/api/bootstrap", response_model=BootstrapResponse)
    async def api_bootstrap():
        channels = channel_service.list_channels()
        config = store.load_config()
        channel_name_by_id = channel_name_map(channels)
        recent_events = [serialize_event(event, channel_name_by_id) for event in store.read_recent_events(16)]
        return serialize_bootstrap(channels, config.model_dump(mode="json"), recent_events)

    @app.get("/api/bootstrap/stream")
    async def api_bootstrap_stream():
        async def event_generator():
            last_payload = ""
            while True:
                channels = channel_service.list_channels()
                config = store.load_config()
                channel_name_by_id = channel_name_map(channels)
                recent_events = [serialize_event(event, channel_name_by_id) for event in store.read_recent_events(16)]
                payload = serialize_bootstrap(channels, config.model_dump(mode="json"), recent_events)
                serialized = json.dumps(payload, ensure_ascii=False)
                if serialized != last_payload:
                    yield f"data: {serialized}\n\n"
                    last_payload = serialized
                else:
                    yield ": keepalive\n\n"
                await asyncio.sleep(3)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
