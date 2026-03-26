from __future__ import annotations

import signal
import threading
import time

from .bootstrap import build_services


services = build_services()
_shutdown = threading.Event()


def _handle_signal(_signum, _frame) -> None:
    _shutdown.set()


def run() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    services.scheduler_service.start()
    try:
        while not _shutdown.is_set():
            time.sleep(1)
    finally:
        services.scheduler_service.stop()


if __name__ == "__main__":
    run()
