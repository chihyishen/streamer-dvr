from __future__ import annotations

import hashlib
import random
from datetime import timedelta

from .time import utc_now


def stable_jitter_seconds(channel_id: str, interval_seconds: int) -> int:
    max_jitter = max(1, int(interval_seconds * 0.3))
    seed = int(hashlib.sha256(channel_id.encode("utf-8")).hexdigest(), 16)
    return random.Random(seed).randint(0, max_jitter)


def compute_next_check_at(channel_id: str, interval_seconds: int, backoff_seconds: int = 0) -> str:
    delay = interval_seconds + stable_jitter_seconds(channel_id, interval_seconds) + backoff_seconds
    return (utc_now() + timedelta(seconds=delay)).isoformat()


def compute_warmup_check_at(channel_id: str, min_delay_seconds: int = 30, max_delay_seconds: int = 120) -> str:
    window = max(min_delay_seconds, max_delay_seconds) - min_delay_seconds
    seed = int(hashlib.sha256(f"warmup:{channel_id}".encode("utf-8")).hexdigest(), 16)
    jitter = random.Random(seed).randint(0, max(0, window))
    return (utc_now() + timedelta(seconds=min_delay_seconds + jitter)).isoformat()
