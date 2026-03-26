from __future__ import annotations

import re
from pathlib import Path

from ..domain import AppConfig, Channel, ErrorCode, Platform
from .base import EnsureDependency, PlatformAdapter, PlatformProbeResult, RecordingFailure


class ChaturbatePlatform(PlatformAdapter):
    key = Platform.CHATURBATE
    USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")

    def _last_meaningful_line(self, output: str) -> str:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if not lines:
            return "Probe failed"
        return lines[-1]

    def normalize_url(self, username: str, url: str | None) -> str:
        return (url or f"https://chaturbate.com/{username}").strip()

    def validate_username(self, username: str) -> None:
        if not self.USERNAME_PATTERN.fullmatch(username):
            raise ValueError("Chaturbate streamer names only support English letters, numbers, and underscore")

    def probe_command(self, channel: Channel, config: AppConfig, use_cookies: bool, ensure_dependency: EnsureDependency) -> list[str]:
        yt_dlp = ensure_dependency("yt-dlp", config.yt_dlp_path)
        command = [
            yt_dlp,
            "--skip-download",
            "--print",
            "is_live",
            channel.url,
        ]
        
        # Read from the exported cookie file to avoid browser lock and permission issues.
        local_cookies = Path("streamer_cookies.txt")
        if use_cookies and local_cookies.exists():
            command[1:1] = ["--cookies", str(local_cookies)]
            
        return command

    def interpret_probe_result(self, output: str, return_code: int) -> PlatformProbeResult:
        lowered = output.lower()
        if "room is currently offline" in lowered:
            return PlatformProbeResult(False, "Streamer offline", raw_output=output, return_code=return_code)
        if "performer is currently away" in lowered:
            return PlatformProbeResult(False, "Streamer offline (away)", raw_output=output, return_code=return_code)
        if "private show" in lowered or "private session" in lowered:
            return PlatformProbeResult(False, "Streamer unavailable (private show)", raw_output=output, return_code=return_code)
        if "hidden session in progress" in lowered:
            return PlatformProbeResult(
                False,
                "Hidden session in progress",
                ErrorCode.AUTH_OR_COOKIE_FAILED,
                raw_output=output,
                return_code=return_code,
            )
        if return_code == 0 and "True" in output:
            return PlatformProbeResult(True, "Streamer is live", raw_output=output, return_code=return_code)
        if return_code == 0 and "False" in output:
            return PlatformProbeResult(False, "Streamer offline", raw_output=output, return_code=return_code)
        if "403" in output or "401" in output or "cookie" in lowered or "cannot decrypt" in lowered or "login required" in lowered:
            return PlatformProbeResult(False, "Auth/cookie failure", ErrorCode.AUTH_OR_COOKIE_FAILED, raw_output=output, return_code=return_code)
        if "failed to download m3u8 information" in lowered and "404" in lowered:
            return PlatformProbeResult(
                False, "Stream source unstable (m3u8 404)", None, raw_output=output, return_code=return_code
            )
        if "#extm3u absent" in lowered:
            return PlatformProbeResult(
                False, "Stream source unstable (playlist parse failed)", None, raw_output=output, return_code=return_code
            )
        if "timed out" in lowered or "deadline exceeded" in lowered:
            return PlatformProbeResult(False, "Probe timed out", ErrorCode.TIMEOUT, raw_output=output, return_code=return_code)
        if "unable to download webpage" in lowered or "unable to extract" in lowered:
            return PlatformProbeResult(False, "Page fetch failed", ErrorCode.PAGE_FETCH_FAILED, raw_output=output, return_code=return_code)
        if return_code != 0:
            return PlatformProbeResult(
                False,
                self._last_meaningful_line(output),
                ErrorCode.PAGE_FETCH_FAILED,
                raw_output=output,
                return_code=return_code,
            )
        return PlatformProbeResult(False, "Streamer offline", raw_output=output, return_code=return_code)

    def build_record_command(
        self,
        channel: Channel,
        config: AppConfig,
        output_path: Path,
        ensure_dependency: EnsureDependency,
        format_selector: str,
    ) -> list[str]:
        yt_dlp = ensure_dependency("yt-dlp", config.yt_dlp_path)
        command = [
            yt_dlp,
            channel.url,
            "-f",
            format_selector,
            "--no-part",
            "--merge-output-format",
            "mkv",
            "-o",
            str(output_path),
        ]
        
        # Read from the exported cookie file to avoid browser lock and permission issues.
        local_cookies = Path("streamer_cookies.txt")
        if local_cookies.exists():
            command[1:1] = ["--cookies", str(local_cookies)]
            
        return command

    def map_recording_failure(self, stderr: str, return_code: int) -> RecordingFailure:
        lowered = stderr.lower()
        friendly_error = stderr.strip() or f"Recorder exited with code {return_code}"
        error_code = ErrorCode.RECORDER_EXITED
        if "private show" in lowered or "private session" in lowered:
            return RecordingFailure(ErrorCode.RECORDER_EXITED, "Streamer unavailable (private show)", raw_output=stderr, return_code=return_code)
        if "performer is currently away" in lowered:
            return RecordingFailure(ErrorCode.RECORDER_EXITED, "Streamer offline (away)", raw_output=stderr, return_code=return_code)
        if "#extm3u absent" in lowered:
            return RecordingFailure(
                ErrorCode.RECORDER_EXITED,
                "Stream source unstable (playlist parse failed)",
                raw_output=stderr,
                return_code=return_code,
            )
        if "failed to download m3u8 information" in lowered and "404" in lowered:
            return RecordingFailure(
                ErrorCode.RECORDER_EXITED,
                "Stream source unstable (m3u8 404)",
                raw_output=stderr,
                return_code=return_code,
            )
        if "403" in stderr or "401" in stderr or "cookie" in lowered:
            return RecordingFailure(ErrorCode.AUTH_OR_COOKIE_FAILED, friendly_error, raw_output=stderr, return_code=return_code)
        if "timed out" in lowered or "deadline exceeded" in lowered:
            return RecordingFailure(ErrorCode.TIMEOUT, friendly_error, raw_output=stderr, return_code=return_code)
        return RecordingFailure(error_code, friendly_error, raw_output=stderr, return_code=return_code)
