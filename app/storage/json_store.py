from __future__ import annotations

from pathlib import Path

from ..core import CHANNELS_PATH, CONFIG_PATH, EVENT_DB_PATH, LEGACY_LOG_PATH
from .sqlite_store import SQLiteStore


class JsonStore(SQLiteStore):
    def __init__(
        self,
        *,
        config_path: Path = CONFIG_PATH,
        channels_path: Path = CHANNELS_PATH,
        event_db_path: Path = EVENT_DB_PATH,
        legacy_log_path: Path = LEGACY_LOG_PATH,
    ) -> None:
        super().__init__(
            config_path=config_path,
            channels_path=channels_path,
            event_db_path=event_db_path,
            legacy_log_path=legacy_log_path,
        )
