from __future__ import annotations

from fastapi import FastAPI


def register_health_routes(app: FastAPI) -> None:
    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}
