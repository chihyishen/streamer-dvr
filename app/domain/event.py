from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .enums import CommandType


class Event(BaseModel):
    timestamp: str
    level: str
    event_type: str
    channel_id: str | None = None
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Command(BaseModel):
    id: int | None = None
    created_at: str
    type: CommandType
    channel_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
