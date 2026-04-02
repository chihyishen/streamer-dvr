from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from ..common import utc_now_iso
from ..core import CHANNELS_PATH, CONFIG_PATH, EVENT_DB_PATH, LEGACY_LOG_PATH
from ..domain import (
    AppConfig,
    Channel,
    Command,
    CommandType,
    Event,
    FailureCategory,
    RecordingSession,
    RecordingSessionPhase,
    RecordingSessionStatus,
    ResolvedSource,
    SessionEvent,
    SourceAuthMode,
)
from .event_queries import build_event_filters
from .session_queries import build_session_filters
from .sqlite_schema import (
    CHANNELS_TABLE_SQL,
    COMMAND_TABLE_SQL,
    EVENT_TABLE_SQL,
    INDEX_STATEMENTS,
    RESOLVED_SOURCE_TABLE_SQL,
    SCHEMA_VERSION,
    SESSION_EVENT_TABLE_SQL,
    SESSION_TABLE_SQL,
    SETTINGS_TABLE_SQL,
)


class SQLiteStore:
    def __init__(
        self,
        *,
        config_path: Path = CONFIG_PATH,
        channels_path: Path = CHANNELS_PATH,
        event_db_path: Path = EVENT_DB_PATH,
        legacy_log_path: Path = LEGACY_LOG_PATH,
        lock: RLock | None = None,
    ) -> None:
        self._config_path = config_path
        self._channels_path = channels_path
        self._event_db_path = event_db_path
        self._legacy_log_path = legacy_log_path
        self._lock = lock or RLock()
        self._ready = False

    def ensure_files(self) -> None:
        with self._lock:
            if self._ready:
                return
            self._event_db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._ensure_schema_unlocked(connection)
                self._import_legacy_state_unlocked(connection)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._ready = True

    def load_config(self) -> AppConfig:
        with self._lock:
            self._ensure_ready_unlocked()
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT payload_json FROM settings WHERE key = ?",
                    ("app_config",),
                ).fetchone()
        if not row:
            return AppConfig()
        return AppConfig.model_validate(json.loads(row["payload_json"]))

    def save_config(self, config: AppConfig) -> None:
        with self._lock:
            self._ensure_ready_unlocked()
            payload_json = json.dumps(config.model_dump(mode="json"), ensure_ascii=True)
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO settings (key, updated_at, payload_json)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        updated_at = excluded.updated_at,
                        payload_json = excluded.payload_json
                    """,
                    ("app_config", utc_now_iso(), payload_json),
                )

    def load_channels(self) -> list[Channel]:
        with self._lock:
            self._ensure_ready_unlocked()
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT payload_json
                    FROM channels
                    ORDER BY created_at ASC, id ASC
                    """
                ).fetchall()
        return [Channel.model_validate(json.loads(row["payload_json"])) for row in rows]

    def save_channels(self, channels: list[Channel]) -> None:
        with self._lock:
            self._ensure_ready_unlocked()
            rows = [
                (
                    channel.id,
                    int(channel.created_at),
                    utc_now_iso(),
                    json.dumps(channel.model_dump(mode="json"), ensure_ascii=True),
                )
                for channel in channels
            ]
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("DELETE FROM channels")
                connection.executemany(
                    """
                    INSERT OR REPLACE INTO channels (id, created_at, updated_at, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    rows,
                )

    def mutate_channels(self, mutator):
        with self._lock:
            self._ensure_ready_unlocked()
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                channels = self._load_channels_unlocked(connection)
                result = mutator(channels)
                self._write_channels_unlocked(connection, channels)
                return result

    def append_event(self, event: Event) -> None:
        with self._lock:
            self._ensure_ready_unlocked()
            self._insert_events([event])

    def log_info(self, event_type: str, message: str, channel_id: str | None = None, **metadata: object) -> None:
        self._log_event("INFO", event_type, message, channel_id, **metadata)

    def log_error(self, event_type: str, message: str, channel_id: str | None = None, **metadata: object) -> None:
        self._log_event("ERROR", event_type, message, channel_id, **metadata)

    def enqueue_command(self, command_type: CommandType, channel_id: str, **payload: object) -> int:
        with self._lock:
            self._ensure_ready_unlocked()
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    INSERT INTO commands (created_at, type, channel_id, payload_json, claimed_at, completed_at)
                    VALUES (?, ?, ?, ?, NULL, NULL)
                    """,
                    (utc_now_iso(), command_type.value, channel_id, json.dumps(payload, ensure_ascii=True)),
                )
                return int(cursor.lastrowid)

    def claim_pending_commands(self, limit: int = 50) -> list[Command]:
        with self._lock:
            self._ensure_ready_unlocked()
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT id, created_at, type, channel_id, payload_json
                    FROM commands
                    WHERE completed_at IS NULL AND claimed_at IS NULL
                    ORDER BY created_at ASC, id ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                if not rows:
                    return []
                connection.execute("BEGIN IMMEDIATE")
                claimed_at = utc_now_iso()
                command_ids = [int(row["id"]) for row in rows]
                placeholders = ",".join("?" for _ in command_ids)
                connection.execute(
                    f"UPDATE commands SET claimed_at = ? WHERE id IN ({placeholders})",
                    [claimed_at, *command_ids],
                )
        return [
            Command(
                id=int(row["id"]),
                created_at=row["created_at"],
                type=CommandType(row["type"]),
                channel_id=row["channel_id"],
                payload=json.loads(row["payload_json"] or "{}"),
            )
            for row in rows
        ]

    def complete_command(self, command_id: int) -> None:
        with self._lock:
            self._ensure_ready_unlocked()
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE commands SET completed_at = ? WHERE id = ?",
                    (utc_now_iso(), command_id),
                )

    def read_recent_events(self, limit: int = 100) -> list[dict]:
        with self._lock:
            self._ensure_ready_unlocked()
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
            self._ensure_ready_unlocked()
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
            self._ensure_ready_unlocked()
            where_clause, values = build_event_filters(channel_id=channel_id, event_type=event_type, level=level)
            query = f"SELECT COUNT(*) AS count FROM events {where_clause}"
            with self._connect() as connection:
                row = connection.execute(query, values).fetchone()
        return int(row["count"]) if row else 0

    def create_session(self, session: RecordingSession) -> RecordingSession:
        with self._lock:
            self._ensure_ready_unlocked()
            self._upsert_session_unlocked(session)
            return self.get_session(session.id)

    def update_session(self, session_id: str, **changes: object) -> RecordingSession:
        with self._lock:
            self._ensure_ready_unlocked()
            current = self.get_session(session_id)
            changes.setdefault("updated_at", utc_now_iso())
            payload = current.model_dump(mode="json")
            payload.update(self._normalize_session_changes(changes))
            update = RecordingSession.model_validate(payload)
            self._upsert_session_unlocked(update)
            return self.get_session(session_id)

    def get_session(self, session_id: str) -> RecordingSession:
        with self._lock:
            self._ensure_ready_unlocked()
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT *
                    FROM recording_sessions
                    WHERE id = ?
                    """,
                    (session_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(session_id)
                return self._hydrate_session(connection, row)

    def list_sessions(
        self,
        limit: int = 100,
        offset: int = 0,
        *,
        channel_id: str | None = None,
        status: str | None = None,
        phase: str | None = None,
        active_only: bool = False,
    ) -> list[RecordingSession]:
        with self._lock:
            self._ensure_ready_unlocked()
            where_clause, values = build_session_filters(
                channel_id=channel_id,
                status=status,
                phase=phase,
                active_only=active_only,
            )
            query = f"""
                SELECT *
                FROM recording_sessions
                {where_clause}
                ORDER BY updated_at DESC, created_at DESC, id DESC
                LIMIT ? OFFSET ?
            """
            values.extend([limit, offset])
            with self._connect() as connection:
                rows = connection.execute(query, values).fetchall()
                return [self._hydrate_session(connection, row) for row in rows]

    def list_active_sessions(self, limit: int = 100, offset: int = 0) -> list[RecordingSession]:
        return self.list_sessions(limit=limit, offset=offset, active_only=True)

    def read_recent_sessions(self, limit: int = 100, offset: int = 0) -> list[RecordingSession]:
        return self.list_sessions(limit=limit, offset=offset)

    def read_active_sessions(self, limit: int = 100, offset: int = 0) -> list[RecordingSession]:
        return self.list_sessions(limit=limit, offset=offset, active_only=True)

    def count_sessions(
        self,
        *,
        channel_id: str | None = None,
        status: str | None = None,
        phase: str | None = None,
        active_only: bool = False,
    ) -> int:
        with self._lock:
            self._ensure_ready_unlocked()
            where_clause, values = build_session_filters(
                channel_id=channel_id,
                status=status,
                phase=phase,
                active_only=active_only,
            )
            query = f"SELECT COUNT(*) AS count FROM recording_sessions {where_clause}"
            with self._connect() as connection:
                row = connection.execute(query, values).fetchone()
        return int(row["count"]) if row else 0

    def upsert_resolved_source(self, source: ResolvedSource) -> ResolvedSource:
        with self._lock:
            self._ensure_ready_unlocked()
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO resolved_sources (
                        id,
                        session_id,
                        resolver_tool,
                        candidate_index,
                        candidate_url,
                        stream_url,
                        room_status,
                        auth_mode,
                        source_variant,
                        source_fingerprint,
                        validated_at,
                        expires_at,
                        message,
                        raw_output,
                        return_code,
                        metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        session_id = excluded.session_id,
                        resolver_tool = excluded.resolver_tool,
                        candidate_index = excluded.candidate_index,
                        candidate_url = excluded.candidate_url,
                        stream_url = excluded.stream_url,
                        room_status = excluded.room_status,
                        auth_mode = excluded.auth_mode,
                        source_variant = excluded.source_variant,
                        source_fingerprint = excluded.source_fingerprint,
                        validated_at = excluded.validated_at,
                        expires_at = excluded.expires_at,
                        message = excluded.message,
                        raw_output = excluded.raw_output,
                        return_code = excluded.return_code,
                        metadata_json = excluded.metadata_json
                    """,
                    self._resolved_source_row(source),
                )
            return source

    def link_session_resolved_source(self, session_id: str, source: ResolvedSource) -> RecordingSession:
        self.upsert_resolved_source(source)
        return self.update_session(
            session_id,
            active_resolved_source_id=source.id,
            current_phase=RecordingSessionPhase.RESOLVING_SOURCE,
        )

    def get_resolved_source(self, source_id: str) -> ResolvedSource:
        with self._lock:
            self._ensure_ready_unlocked()
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM resolved_sources WHERE id = ?",
                    (source_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(source_id)
                return self._row_to_resolved_source(row)

    def append_session_event(self, event: SessionEvent) -> int:
        with self._lock:
            self._ensure_ready_unlocked()
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    INSERT INTO session_events (
                        session_id,
                        timestamp,
                        phase,
                        level,
                        event_type,
                        failure_category,
                        message,
                        metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._session_event_row(event),
                )
                return int(cursor.lastrowid)

    def read_session_events(
        self,
        session_id: str | None = None,
        *,
        limit: int = 200,
        offset: int = 0,
        phase: str | None = None,
        failure_category: str | None = None,
    ) -> list[SessionEvent]:
        with self._lock:
            self._ensure_ready_unlocked()
            conditions: list[str] = []
            values: list[object] = []
            if session_id:
                conditions.append("session_id = ?")
                values.append(session_id)
            if phase:
                conditions.append("phase = ?")
                values.append(getattr(phase, "value", phase))
            if failure_category:
                conditions.append("failure_category = ?")
                values.append(getattr(failure_category, "value", failure_category))
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            query = f"""
                SELECT *
                FROM session_events
                {where_clause}
                ORDER BY timestamp DESC, id DESC
                LIMIT ? OFFSET ?
            """
            values.extend([limit, offset])
            with self._connect() as connection:
                rows = connection.execute(query, values).fetchall()
        return [self._row_to_session_event(row) for row in rows]

    def count_session_events(
        self,
        session_id: str | None = None,
        *,
        phase: str | None = None,
        failure_category: str | None = None,
    ) -> int:
        with self._lock:
            self._ensure_ready_unlocked()
            conditions: list[str] = []
            values: list[object] = []
            if session_id:
                conditions.append("session_id = ?")
                values.append(session_id)
            if phase:
                conditions.append("phase = ?")
                values.append(getattr(phase, "value", phase))
            if failure_category:
                conditions.append("failure_category = ?")
                values.append(getattr(failure_category, "value", failure_category))
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            query = f"SELECT COUNT(*) AS count FROM session_events {where_clause}"
            with self._connect() as connection:
                row = connection.execute(query, values).fetchone()
        return int(row["count"]) if row else 0

    def _ensure_ready_unlocked(self) -> None:
        if not self._ready:
            self.ensure_files()

    def _log_event(self, level: str, event_type: str, message: str, channel_id: str | None, **metadata: object) -> None:
        normalized_metadata = {key: value for key, value in metadata.items() if value is not None}
        self.append_event(
            Event(
                timestamp=utc_now_iso(),
                level=level,
                event_type=event_type,
                channel_id=channel_id,
                message=message,
                metadata=normalized_metadata,
            )
        )

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self._event_db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _ensure_schema_unlocked(self, connection: sqlite3.Connection) -> None:
        connection.execute(SETTINGS_TABLE_SQL)
        connection.execute(CHANNELS_TABLE_SQL)
        connection.execute(EVENT_TABLE_SQL)
        connection.execute(COMMAND_TABLE_SQL)
        connection.execute(SESSION_TABLE_SQL)
        connection.execute(RESOLVED_SOURCE_TABLE_SQL)
        connection.execute(SESSION_EVENT_TABLE_SQL)
        for statement in INDEX_STATEMENTS:
            connection.execute(statement)

    def _import_legacy_state_unlocked(self, connection: sqlite3.Connection) -> None:
        self._import_config_unlocked(connection)
        self._import_channels_unlocked(connection)
        self._import_legacy_events_unlocked(connection)

    def _import_config_unlocked(self, connection: sqlite3.Connection) -> None:
        row = connection.execute("SELECT 1 FROM settings WHERE key = ?", ("app_config",)).fetchone()
        if row is not None:
            return
        config = AppConfig()
        if self._config_path.exists():
            payload = json.loads(self._config_path.read_text(encoding="utf-8"))
            config = AppConfig.model_validate(payload)
        connection.execute(
            """
            INSERT INTO settings (key, updated_at, payload_json)
            VALUES (?, ?, ?)
            """,
            ("app_config", utc_now_iso(), json.dumps(config.model_dump(mode="json"), ensure_ascii=True)),
        )

    def _import_channels_unlocked(self, connection: sqlite3.Connection) -> None:
        row = connection.execute("SELECT 1 FROM channels LIMIT 1").fetchone()
        if row is not None or not self._channels_path.exists():
            return
        payload = json.loads(self._channels_path.read_text(encoding="utf-8"))
        channels = [Channel.model_validate(item) for item in payload]
        self._write_channels_unlocked(connection, channels)

    def _import_legacy_events_unlocked(self, connection: sqlite3.Connection) -> None:
        row = connection.execute("SELECT 1 FROM events LIMIT 1").fetchone()
        if row is not None or not self._legacy_log_path.exists():
            return
        lines = self._legacy_log_path.read_text(encoding="utf-8").splitlines()
        events: list[Event] = []
        for line in lines:
            if not line.strip():
                continue
            payload = json.loads(line)
            events.append(Event.model_validate(payload))
        if events:
            self._insert_events(events, connection=connection)

    def _load_channels_unlocked(self, connection: sqlite3.Connection) -> list[Channel]:
        rows = connection.execute(
            """
            SELECT payload_json
            FROM channels
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
        return [Channel.model_validate(json.loads(row["payload_json"])) for row in rows]

    def _write_channels_unlocked(self, connection: sqlite3.Connection, channels: list[Channel]) -> None:
        rows = [
            (
                channel.id,
                int(channel.created_at),
                utc_now_iso(),
                json.dumps(channel.model_dump(mode="json"), ensure_ascii=True),
            )
            for channel in channels
        ]
        connection.execute("DELETE FROM channels")
        if rows:
            connection.executemany(
                """
                INSERT OR REPLACE INTO channels (id, created_at, updated_at, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )

    def _insert_events(self, events: list[Event], *, connection: sqlite3.Connection | None = None) -> None:
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
        if connection is None:
            with self._connect() as connection_obj:
                connection_obj.execute("BEGIN IMMEDIATE")
                connection_obj.executemany(
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
            return
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

    def _row_to_event_dict(self, row: sqlite3.Row) -> dict:
        payload = dict(row)
        metadata = payload.pop("metadata_json", "{}")
        payload["metadata"] = json.loads(metadata) if metadata else {}
        return payload

    def _row_to_session_event(self, row: sqlite3.Row) -> SessionEvent:
        payload = dict(row)
        metadata = payload.pop("metadata_json", "{}")
        payload["metadata"] = json.loads(metadata) if metadata else {}
        payload["phase"] = RecordingSessionPhase(payload["phase"])
        failure_category = payload.get("failure_category")
        payload["failure_category"] = FailureCategory(failure_category) if failure_category else None
        return SessionEvent.model_validate(payload)

    def _session_event_row(self, event: SessionEvent) -> tuple[object, ...]:
        return (
            event.session_id,
            event.timestamp,
            event.phase.value,
            event.level,
            event.event_type,
            event.failure_category.value if event.failure_category else None,
            event.message,
            json.dumps(event.metadata, ensure_ascii=True),
        )

    def _row_to_resolved_source(self, row: sqlite3.Row) -> ResolvedSource:
        payload = dict(row)
        metadata = payload.pop("metadata_json", "{}")
        payload["metadata"] = json.loads(metadata) if metadata else {}
        payload["auth_mode"] = SourceAuthMode(payload["auth_mode"])
        return ResolvedSource.model_validate(payload)

    def _resolved_source_row(self, source: ResolvedSource) -> tuple[object, ...]:
        return (
            source.id,
            source.session_id,
            source.resolver_tool,
            source.candidate_index,
            source.candidate_url,
            source.stream_url,
            source.room_status,
            source.auth_mode.value,
            source.source_variant,
            source.source_fingerprint,
            source.validated_at,
            source.expires_at,
            source.message,
            source.raw_output,
            source.return_code,
            json.dumps(source.metadata, ensure_ascii=True),
        )

    def _hydrate_session(self, connection: sqlite3.Connection, row: sqlite3.Row) -> RecordingSession:
        payload = dict(row)
        metadata = payload.pop("metadata_json", "{}")
        payload["metadata"] = json.loads(metadata) if metadata else {}
        payload["status"] = RecordingSessionStatus(payload["status"])
        payload["current_phase"] = RecordingSessionPhase(payload["current_phase"])
        failure_category = payload.get("final_failure_category")
        payload["final_failure_category"] = FailureCategory(failure_category) if failure_category else None
        session = RecordingSession.model_validate(payload)
        if session.active_resolved_source_id:
            try:
                session = session.model_copy(
                    update={"active_resolved_source": self.get_resolved_source(session.active_resolved_source_id)}
                )
            except KeyError:
                session = session.model_copy(update={"active_resolved_source": None})
        return session

    def _session_row(self, session: RecordingSession) -> tuple[object, ...]:
        return (
            session.id,
            session.channel_id,
            session.status.value,
            session.current_phase.value,
            session.created_at,
            session.updated_at,
            session.started_at,
            session.ended_at,
            session.last_heartbeat_at,
            session.active_pid,
            session.active_resolved_source_id,
            session.final_failure_category.value if session.final_failure_category else None,
            session.final_failure_message,
            json.dumps(session.metadata, ensure_ascii=True),
        )

    def _normalize_session_changes(self, changes: dict[str, object]) -> dict[str, object]:
        normalized = dict(changes)
        if "status" in normalized and normalized["status"] is not None:
            normalized["status"] = getattr(normalized["status"], "value", normalized["status"])
        if "current_phase" in normalized and normalized["current_phase"] is not None:
            normalized["current_phase"] = getattr(normalized["current_phase"], "value", normalized["current_phase"])
        if "final_failure_category" in normalized and normalized["final_failure_category"] is not None:
            normalized["final_failure_category"] = getattr(
                normalized["final_failure_category"], "value", normalized["final_failure_category"]
            )
        return normalized

    def _upsert_session_unlocked(self, session: RecordingSession) -> None:
        if session.active_resolved_source is not None:
            self.upsert_resolved_source(session.active_resolved_source)
            session = session.model_copy(update={"active_resolved_source_id": session.active_resolved_source.id})
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO recording_sessions (
                    id,
                    channel_id,
                    status,
                    current_phase,
                    created_at,
                    updated_at,
                    started_at,
                    ended_at,
                    last_heartbeat_at,
                    active_pid,
                    active_resolved_source_id,
                    final_failure_category,
                    final_failure_message,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    status = excluded.status,
                    current_phase = excluded.current_phase,
                    updated_at = excluded.updated_at,
                    started_at = excluded.started_at,
                    ended_at = excluded.ended_at,
                    last_heartbeat_at = excluded.last_heartbeat_at,
                    active_pid = excluded.active_pid,
                    active_resolved_source_id = excluded.active_resolved_source_id,
                    final_failure_category = excluded.final_failure_category,
                    final_failure_message = excluded.final_failure_message,
                    metadata_json = excluded.metadata_json
                """,
                self._session_row(session),
            )
