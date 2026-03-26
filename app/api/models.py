from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
from ..domain import AppConfig, Channel

class EventItem(BaseModel):
    timestamp: str
    timestamp_display: str | None = None
    level: str
    event_type: str
    channel_id: str | None = None
    channel_name: str | None = None
    message: str
    summary: str | None = None
    tone: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class ChannelResponse(BaseModel):
    channel: Channel

class ChannelListResponse(BaseModel):
    channels: list[Channel]

class DeleteResponse(BaseModel):
    success: bool
    message: str

class LogsResponse(BaseModel):
    items: list[EventItem]
    event_types: list[str]
    channels: list[dict[str, str]]
    total: int
    limit: int
    offset: int
    has_next: bool

class BootstrapResponse(BaseModel):
    channels: list[Any] # 使用 Any 避免 Pydantic 再次過濾計算欄位
    categories: list[str]
    all_channels_count: int
    config: dict
    recent_events: list[EventItem]
