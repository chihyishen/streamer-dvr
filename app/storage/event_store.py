from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock

from ..domain import Event
from .command_queue import CommandQueue
from .event_repository import EventRepository
from .event_sql import COMMAND_TABLE_SQL, EVENT_TABLE_SQL, INDEX_STATEMENTS


class EventStore(EventRepository, CommandQueue):
    def __init__(self, *, event_db_path: Path, legacy_log_path: Path, lock: RLock) -> None:
        self._event_db_path = event_db_path
        self._legacy_log_path = legacy_log_path
        self._lock = lock

    def ensure_files(self) -> None:
        with self._lock:
            self._ensure_event_db()
            self._migrate_legacy_events_if_needed()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._event_db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_event_db(self) -> None:
        with self._connect() as connection:
            connection.execute(EVENT_TABLE_SQL)
            connection.execute(COMMAND_TABLE_SQL)
            for statement in INDEX_STATEMENTS:
                connection.execute(statement)

    def _migrate_legacy_events_if_needed(self) -> None:
        if self._event_count() > 0 or not self._legacy_log_path.exists():
            return
        lines = self._legacy_log_path.read_text(encoding="utf-8").splitlines()
        events: list[Event] = []
        for line in lines:
            if not line.strip():
                continue
            payload = json.loads(line)
            events.append(Event.model_validate(payload))
        if events:
            self._insert_events(events)
