from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"
CHANNELS_PATH = ROOT_DIR / "channels.json"
EVENT_DB_PATH = ROOT_DIR / "events.db"
LEGACY_LOG_PATH = ROOT_DIR / "events.jsonl"
