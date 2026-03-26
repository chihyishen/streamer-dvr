from __future__ import annotations

from ..domain import AppConfig, AppConfigUpdate
from ..storage import JsonStore


class ConfigService:
    def __init__(self, store: JsonStore) -> None:
        self.store = store

    def get(self) -> AppConfig:
        return self.store.load_config()

    def update(self, payload: AppConfigUpdate) -> AppConfig:
        current = self.store.load_config()
        updated = current.model_copy(update=payload.model_dump())
        self.store.save_config(updated)
        self.store.log_info("config_updated", "Configuration updated")
        return updated
