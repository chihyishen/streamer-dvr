from __future__ import annotations

import json
import sqlite3

from ..domain import Event
from .event_queries import build_event_filters


class EventRepository:
    def _event_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM events").fetchone()
            return int(row["count"]) if row else 0

    def _insert_events(self, events: list[Event]) -> None:
        rows = [
            (
                event.timestamp,
                event.level,
                event.event_type,
                event.channel_id,
                event.message,
                json.dumps(event.metadata, ensure_ascii=True),
            )
            for event in events
        ]
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO events (
                    timestamp,
                    level,
                    event_type,
                    channel_id,
                    message,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def append_event(self, event: Event) -> None:
        with self._lock:
            self._insert_events([event])

    def _row_to_event_dict(self, row: sqlite3.Row) -> dict:
        payload = dict(row)
        metadata = payload.pop("metadata_json", "{}")
        payload["metadata"] = json.loads(metadata) if metadata else {}
        return payload

    def read_recent_events(self, limit: int = 100) -> list[dict]:
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT timestamp, level, event_type, channel_id, message, metadata_json
                    FROM events
                    ORDER BY timestamp DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [self._row_to_event_dict(row) for row in rows]

    def read_events(
        self,
        limit: int = 200,
        offset: int = 0,
        channel_id: str | None = None,
        event_type: str | None = None,
        level: str | None = None,
    ) -> list[dict]:
        with self._lock:
            where_clause, values = build_event_filters(channel_id=channel_id, event_type=event_type, level=level)
            query = f"""
                SELECT timestamp, level, event_type, channel_id, message, metadata_json
                FROM events
                {where_clause}
                ORDER BY timestamp DESC, id DESC
                LIMIT ? OFFSET ?
            """
            values.extend([limit, offset])
            with self._connect() as connection:
                rows = connection.execute(query, values).fetchall()
        return [self._row_to_event_dict(row) for row in rows]

    def count_events(
        self,
        channel_id: str | None = None,
        event_type: str | None = None,
        level: str | None = None,
    ) -> int:
        with self._lock:
            where_clause, values = build_event_filters(channel_id=channel_id, event_type=event_type, level=level)
            query = f"SELECT COUNT(*) AS count FROM events {where_clause}"
            with self._connect() as connection:
                row = connection.execute(query, values).fetchone()
        return int(row["count"]) if row else 0
