from __future__ import annotations

import uvicorn

from .api import create_app
from .bootstrap import build_services


services = build_services()
app = create_app(
    services.store,
    services.channel_service,
    services.config_service,
)


def run() -> None:
    config = services.store.load_config()
    uvicorn.run("app.main:app", host=config.host, port=config.port, reload=False)


if __name__ == "__main__":
    run()
