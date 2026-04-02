from __future__ import annotations

from pydantic import BaseModel


class AppConfig(BaseModel):
    recordings_dir: str = "recordings"
    organized_dir: str = "organized"
    host: str = "0.0.0.0"
    port: int = 8787
    timezone: str = "Asia/Taipei"
    default_poll_interval_seconds: int = 180
    delete_source_after_convert: bool = True
    keep_failed_source: bool = False
    max_concurrent_probes: int = 5
    probe_rate_limit_seconds: int = 5
    probe_timeout_seconds: int = 90
    source_retry_max_attempts: int = 5
    source_retry_initial_delay_seconds: float = 1.0
    source_retry_backoff_multiplier: float = 2.0
    source_retry_max_delay_seconds: float = 16.0
    cookies_from_browser: str = "edge"
    yt_dlp_path: str = "yt-dlp"
    ffmpeg_path: str = "ffmpeg"

    model_config = {"populate_by_name": True}


class AppConfigUpdate(BaseModel):
    host: str
    port: int
    timezone: str
    recordings_dir: str
    organized_dir: str
    default_poll_interval_seconds: int
    max_concurrent_probes: int
    probe_rate_limit_seconds: int
    probe_timeout_seconds: int
    source_retry_max_attempts: int = 5
    source_retry_initial_delay_seconds: float = 1.0
    source_retry_backoff_multiplier: float = 2.0
    source_retry_max_delay_seconds: float = 16.0
    cookies_from_browser: str
    yt_dlp_path: str
    ffmpeg_path: str
    delete_source_after_convert: bool = False
    keep_failed_source: bool = False

    model_config = {"populate_by_name": True}
