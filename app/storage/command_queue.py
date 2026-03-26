from __future__ import annotations

import json

from ..common import utc_now_iso
from ..domain import Command, CommandType


class CommandQueue:
    def enqueue_command(self, command_type: CommandType, channel_id: str, **payload: object) -> int:
        with self._lock:
            with self._connect() as connection:
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
            with self._connect() as connection:
                connection.execute(
                    "UPDATE commands SET completed_at = ? WHERE id = ?",
                    (utc_now_iso(), command_id),
                )
