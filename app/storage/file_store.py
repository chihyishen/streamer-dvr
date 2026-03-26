from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Callable, Iterable, TypeVar

from ..domain import AppConfig, Channel

T = TypeVar("T")


class FileStore:
    def __init__(self, *, config_path: Path, channels_path: Path, lock: RLock) -> None:
        self._config_path = config_path
        self._channels_path = channels_path
        self._config_lock_path = config_path.with_name(f"{config_path.name}.lock")
        self._channels_lock_path = channels_path.with_name(f"{channels_path.name}.lock")
        self._lock = lock

    def ensure_files(self) -> None:
        with self._lock:
            if not self._config_path.exists():
                default_config = AppConfig()
                self._config_path.write_text(
                    json.dumps(default_config.model_dump(mode="json"), indent=2, ensure_ascii=True) + "\n",
                    encoding="utf-8",
                )
            if not self._channels_path.exists():
                self._channels_path.write_text("[]\n", encoding="utf-8")

    def load_config(self) -> AppConfig:
        with self._lock:
            with self._file_lock(self._config_lock_path):
                payload = json.loads(self._config_path.read_text(encoding="utf-8"))
            return AppConfig.model_validate(payload)

    def save_config(self, config: AppConfig) -> None:
        with self._lock:
            with self._file_lock(self._config_lock_path):
                self._config_path.write_text(
                    json.dumps(config.model_dump(mode="json"), indent=2, ensure_ascii=True) + "\n",
                    encoding="utf-8",
                )

    def load_channels(self) -> list[Channel]:
        with self._lock:
            with self._file_lock(self._channels_lock_path):
                return self._load_channels_unlocked()

    def save_channels(self, channels: Iterable[Channel]) -> None:
        with self._lock:
            with self._file_lock(self._channels_lock_path):
                self._write_channels_unlocked(channels)

    def mutate_channels(self, mutator: Callable[[list[Channel]], T]) -> T:
        with self._lock:
            with self._file_lock(self._channels_lock_path):
                channels = self._load_channels_unlocked()
                result = mutator(channels)
                self._write_channels_unlocked(channels)
                return result

    def _load_channels_unlocked(self) -> list[Channel]:
        if not self._channels_path.exists():
            return []
        payload = json.loads(self._channels_path.read_text(encoding="utf-8"))
        return [Channel.model_validate(item) for item in payload]

    def _write_channels_unlocked(self, channels: Iterable[Channel]) -> None:
        data = [channel.model_dump(mode="json") for channel in channels]
        self._channels_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    @contextmanager
    def _file_lock(self, lock_path: Path):
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
