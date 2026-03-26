from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..domain import AppConfig, Channel, ErrorCode, Platform

EnsureDependency = Callable[[str, str | None], str]


@dataclass(frozen=True)
class PlatformProbeResult:
    online: bool
    message: str
    error_code: ErrorCode | None = None
    raw_output: str | None = None
    return_code: int | None = None


@dataclass(frozen=True)
class RecordingFailure:
    error_code: ErrorCode
    message: str
    raw_output: str | None = None
    return_code: int | None = None


class PlatformAdapter:
    key: Platform

    def normalize_url(self, username: str, url: str | None) -> str:
        raise NotImplementedError

    def validate_username(self, username: str) -> None:
        return

    def probe_command(self, channel: Channel, config: AppConfig, use_cookies: bool, ensure_dependency: EnsureDependency) -> list[str]:
        raise NotImplementedError

    def interpret_probe_result(self, output: str, return_code: int) -> PlatformProbeResult:
        raise NotImplementedError

    def build_record_command(
        self,
        channel: Channel,
        config: AppConfig,
        output_path: Path,
        ensure_dependency: EnsureDependency,
        format_selector: str,
    ) -> list[str]:
        raise NotImplementedError

    def recording_extension(self) -> str:
        return "mkv"

    def map_recording_failure(self, stderr: str, return_code: int) -> RecordingFailure:
        raise NotImplementedError
