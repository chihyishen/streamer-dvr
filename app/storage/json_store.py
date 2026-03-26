from __future__ import annotations

import threading

from ..core import CHANNELS_PATH, CONFIG_PATH, EVENT_DB_PATH, LEGACY_LOG_PATH
from ..common import utc_now_iso
from ..domain import AppConfig, Channel, Command, CommandType, Event
from .event_store import EventStore
from .file_store import FileStore


class JsonStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._files = FileStore(config_path=CONFIG_PATH, channels_path=CHANNELS_PATH, lock=self._lock)
        self._events = EventStore(event_db_path=EVENT_DB_PATH, legacy_log_path=LEGACY_LOG_PATH, lock=self._lock)

    def ensure_files(self) -> None:
        self._files.ensure_files()
        self._events.ensure_files()

    def load_config(self) -> AppConfig:
        return self._files.load_config()

    def save_config(self, config: AppConfig) -> None:
        self._files.save_config(config)

    def load_channels(self) -> list[Channel]:
        return self._files.load_channels()

    def save_channels(self, channels: list[Channel]) -> None:
        self._files.save_channels(channels)

    def mutate_channels(self, mutator):
        return self._files.mutate_channels(mutator)

    def append_event(self, event: Event) -> None:
        self._events.append_event(event)

    def enqueue_command(self, command_type: CommandType, channel_id: str, **payload: object) -> int:
        return self._events.enqueue_command(command_type, channel_id, **payload)

    def claim_pending_commands(self, limit: int = 50) -> list[Command]:
        return self._events.claim_pending_commands(limit)

    def complete_command(self, command_id: int) -> None:
        self._events.complete_command(command_id)

    def read_recent_events(self, limit: int = 100) -> list[dict]:
        return self._events.read_recent_events(limit)

    def read_events(
        self,
        limit: int = 200,
        offset: int = 0,
        channel_id: str | None = None,
        event_type: str | None = None,
        level: str | None = None,
    ) -> list[dict]:
        return self._events.read_events(limit=limit, offset=offset, channel_id=channel_id, event_type=event_type, level=level)

    def count_events(
        self,
        channel_id: str | None = None,
        event_type: str | None = None,
        level: str | None = None,
    ) -> int:
        return self._events.count_events(channel_id=channel_id, event_type=event_type, level=level)

    def log_info(self, event_type: str, message: str, channel_id: str | None = None, **metadata: object) -> None:
        self.append_event(
            Event(
                timestamp=utc_now_iso(),
                level="INFO",
                event_type=event_type,
                channel_id=channel_id,
                message=message,
                metadata=metadata,
            )
        )

    def log_error(self, event_type: str, message: str, channel_id: str | None = None, **metadata: object) -> None:
        self.append_event(
            Event(
                timestamp=utc_now_iso(),
                level="ERROR",
                event_type=event_type,
                channel_id=channel_id,
                message=message,
                metadata=metadata,
            )
        )
