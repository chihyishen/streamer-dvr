from __future__ import annotations

from fastapi import Body, FastAPI

from ...domain import AppConfig, AppConfigUpdate
from ...services import ConfigService
from ...storage import JsonStore


def register_settings_routes(app: FastAPI, *, store: JsonStore, config_service: ConfigService) -> None:
    @app.get("/api/settings", response_model=AppConfig)
    async def api_settings():
        return store.load_config().model_dump(mode="json")

    @app.put("/api/settings", response_model=AppConfig)
    async def api_update_settings(payload: AppConfigUpdate = Body(...)):
        config = config_service.update(payload)
        return config.model_dump(mode="json")
