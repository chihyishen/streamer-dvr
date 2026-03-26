from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from ..services import ChannelService, ConfigService
from ..storage import JsonStore
from .routes import (
    register_bootstrap_routes,
    register_channel_routes,
    register_health_routes,
    register_log_routes,
    register_settings_routes,
)


def create_app(
    store: JsonStore,
    channel_service: ChannelService,
    config_service: ConfigService,
    lifespan: Callable | None = None,
) -> FastAPI:
    dist_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    app = FastAPI(title="Streamer DVR", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_bootstrap_routes(app, store=store, channel_service=channel_service)
    register_channel_routes(app, store=store, channel_service=channel_service)
    register_log_routes(app, store=store, channel_service=channel_service)
    register_settings_routes(app, store=store, config_service=config_service)
    register_health_routes(app)

    @app.get("/")
    async def index():
        if dist_dir.exists():
            return FileResponse(dist_dir / "index.html")
        return JSONResponse(
            {
                "service": "streamer-dvr-api",
                "status": "ok",
                "frontend": "Build frontend with `npm run build --prefix frontend` to serve the dashboard from FastAPI.",
            }
        )

    @app.get("/{full_path:path}")
    async def frontend(full_path: str):
        if not dist_dir.exists():
            return JSONResponse(
                {
                    "detail": "Frontend build not found.",
                    "hint": "Run `npm run build --prefix frontend` or use `npm run dev --prefix frontend` during development.",
                },
                status_code=404,
            )
        candidate = (dist_dir / full_path).resolve()
        if candidate.is_file() and dist_dir in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist_dir / "index.html")

    return app
