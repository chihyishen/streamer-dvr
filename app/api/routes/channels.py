from __future__ import annotations

from fastapi import Body, FastAPI, HTTPException

from ...domain import ChannelCreate, ChannelUpdate, CommandType
from ...services import ChannelService
from ...storage import JsonStore
from ..models import ChannelListResponse, ChannelResponse, DeleteResponse
from ..serializers import serialize_channel


def register_channel_routes(app: FastAPI, *, store: JsonStore, channel_service: ChannelService) -> None:
    @app.get("/api/channels", response_model=ChannelListResponse)
    async def api_channels():
        channels = channel_service.list_channels()
        return ChannelListResponse(items=[serialize_channel(channel) for channel in channels])

    @app.post("/api/channels", response_model=ChannelResponse)
    async def api_create_channel(payload: ChannelCreate = Body(...)):
        config = store.load_config()
        try:
            created = channel_service.create(payload, config)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not created.paused and created.enabled:
            store.enqueue_command(CommandType.CHECK, created.id, reason="channel_created")
        return serialize_channel(created)

    @app.patch("/api/channels/{channel_id}", response_model=ChannelResponse)
    async def api_update_channel(channel_id: str, payload: ChannelUpdate = Body(...)):
        try:
            updated = channel_service.update(channel_id, payload, store.load_config())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown channel: {channel_id}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return serialize_channel(updated)

    @app.delete("/api/channels/{channel_id}", response_model=DeleteResponse)
    async def api_delete_channel(channel_id: str):
        try:
            channel = channel_service.get_channel(channel_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown channel: {channel_id}") from exc
        if channel.status == "recording" or channel.active_pid:
            channel_service.update(channel_id, ChannelUpdate(enabled=False, paused=True), store.load_config())
            store.enqueue_command(CommandType.DELETE, channel_id, reason="channel_deleted")
        else:
            channel_service.delete(channel_id)
        return DeleteResponse(ok=True)

    @app.post("/api/channels/{channel_id}/pause", response_model=ChannelResponse)
    async def api_pause_channel(channel_id: str):
        try:
            updated = channel_service.set_paused(channel_id, True, store.load_config(), log_event=False)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown channel: {channel_id}") from exc
        store.enqueue_command(CommandType.PAUSE, channel_id, reason="user_pause")
        return serialize_channel(updated)

    @app.post("/api/channels/{channel_id}/resume", response_model=ChannelResponse)
    async def api_resume_channel(channel_id: str):
        try:
            updated = channel_service.set_paused(channel_id, False, store.load_config(), log_event=False)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown channel: {channel_id}") from exc
        store.enqueue_command(CommandType.RESUME, channel_id, reason="user_resume")
        return serialize_channel(updated)

    @app.post("/api/channels/{channel_id}/check", response_model=ChannelResponse)
    async def api_check_channel(channel_id: str):
        try:
            channel = channel_service.get_channel(channel_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown channel: {channel_id}") from exc
        store.enqueue_command(CommandType.CHECK, channel_id, reason="manual_check")
        return serialize_channel(channel)
