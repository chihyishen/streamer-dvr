from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from ..domain import AppConfig, Channel, ErrorCode, Platform
from .base import EnsureDependency, PlatformAdapter, PlatformProbeResult, RecordingFailure, StreamSourceResult


class ChaturbatePlatform(PlatformAdapter):
    key = Platform.CHATURBATE
    USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
    SOURCE_ENDPOINT = "https://chaturbate.com/api/chatvideocontext/{username}/"
    ORIGIN = "https://chaturbate.com"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    COOKIE_PATH = Path("streamer_cookies.txt")
    RAW_OUTPUT_LIMIT = 4096
    RAW_OUTPUT_LINE_LIMIT = 80

    def _is_hidden_show_message(self, message: str) -> bool:
        lowered = message.lower()
        return any(
            phrase in lowered
            for phrase in (
                "hidden session in progress",
                "secret show",
                "ticket show",
                "hidden cam",
            )
        )

    def _last_meaningful_line(self, output: str) -> str:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if not lines:
            return "Probe failed"
        return lines[-1]

    def _room_referer(self, channel: Channel) -> str:
        return f"{channel.url.rstrip('/')}/"

    def _truncate_raw_output(self, raw_output: str | None) -> str | None:
        if raw_output is None:
            return None
        if len(raw_output) <= self.RAW_OUTPUT_LIMIT:
            return raw_output
        return f"{raw_output[:self.RAW_OUTPUT_LIMIT]}...[truncated]"

    def _truncate_raw_output_tail(self, raw_output: str | None) -> str | None:
        if raw_output is None:
            return None
        lines = raw_output.splitlines()
        if len(lines) > self.RAW_OUTPUT_LINE_LIMIT:
            raw_output = "\n".join(lines[-self.RAW_OUTPUT_LINE_LIMIT :])
        if len(raw_output) <= self.RAW_OUTPUT_LIMIT:
            return raw_output
        return f"[truncated]...{raw_output[-self.RAW_OUTPUT_LIMIT:]}"

    def _extract_source_metadata(self, stream_url: str) -> dict[str, str | int | None]:
        parsed = urlparse(stream_url)
        query = parse_qs(parsed.query)
        expire_value: int | None = None
        token_payload = query.get("t", [None])[0]
        if token_payload:
            try:
                token_data = json.loads(unquote(token_payload))
                expire_raw = token_data.get("expire")
                if expire_raw is not None:
                    expire_value = int(expire_raw)
            except (ValueError, TypeError, json.JSONDecodeError):
                expire_value = None
        return {
            "source_path": parsed.path,
            "source_path_tail": parsed.path.rsplit("/", 1)[-1] or parsed.path,
            "source_expire": expire_value,
        }

    def _expected_unavailable_from_error_body(self, raw_body: str) -> tuple[str, str] | None:
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError:
            lowered = raw_body.lower()
            if "404" in lowered and ("page not found" in lowered or "<title>404" in lowered or "not found" in lowered):
                return "offline", "Streamer unavailable (room not found)"
            return None
        room_status = str(data.get("room_status") or "").lower()
        detail = str(data.get("detail") or "").strip()
        code = str(data.get("code") or "").strip().lower()
        hidden_message = str(data.get("hidden_message") or "").strip()

        if room_status in {"private", "group_show"}:
            return "private", "Streamer unavailable (private show)"
        if room_status == "hidden":
            return "hidden", hidden_message or "Hidden session in progress"
        if code == "password-required" or "requires a password" in detail.lower():
            return "private", "Streamer unavailable (password protected)"
        return None

    def normalize_url(self, username: str, url: str | None) -> str:
        return (url or f"https://chaturbate.com/{username}").strip()

    def record_uses_resolved_source(self) -> bool:
        return True

    def validate_username(self, username: str) -> None:
        if not self.USERNAME_PATTERN.fullmatch(username):
            raise ValueError("Chaturbate streamer names only support English letters, numbers, and underscore")

    def _build_cookie_header(self, include_exported_cookies: bool) -> str:
        cookies: dict[str, str] = {}
        if include_exported_cookies and self.COOKIE_PATH.exists():
            with self.COOKIE_PATH.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) >= 7:
                        cookies[parts[5]] = parts[6]
        return "; ".join(f"{name}={value}" for name, value in cookies.items())

    def _build_resolve_headers(self, channel: Channel, use_cookies: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Origin": self.ORIGIN,
            "Referer": self._room_referer(channel),
            "User-Agent": self.USER_AGENT,
        }
        cookie_header = self._build_cookie_header(use_cookies)
        if cookie_header:
            headers["Cookie"] = cookie_header
        return headers

    def _build_record_headers(self, channel: Channel, *, include_cookies: bool = False) -> str:
        headers = [
            "Accept: application/vnd.apple.mpegurl, application/x-mpegURL, */*",
            f"Origin: {self.ORIGIN}",
            f"Referer: {self._room_referer(channel)}",
        ]
        cookie_header = self._build_cookie_header(include_cookies)
        if cookie_header:
            headers.append(f"Cookie: {cookie_header}")
        return "\r\n".join(headers) + "\r\n"

    def resolve_stream_source(self, channel: Channel, config: AppConfig, use_cookies: bool) -> StreamSourceResult:
        request = urllib.request.Request(
            self.SOURCE_ENDPOINT.format(username=channel.username),
            headers=self._build_resolve_headers(channel, use_cookies),
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=config.probe_timeout_seconds) as response:
                status_code = getattr(response, "status", 200)
                raw_body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw_body = exc.read().decode("utf-8", errors="replace")
            expected_unavailable = self._expected_unavailable_from_error_body(raw_body)
            if expected_unavailable is not None:
                status, message = expected_unavailable
                return StreamSourceResult(
                    status=status,
                    message=message,
                    metadata={"room_status": status},
                    raw_output=self._truncate_raw_output(raw_body),
                    return_code=exc.code,
                )
            error_code = ErrorCode.AUTH_OR_COOKIE_FAILED if exc.code in {401, 403} else ErrorCode.SOURCE_RESOLVE_FAILED
            message = "Auth/cookie failure" if error_code == ErrorCode.AUTH_OR_COOKIE_FAILED else f"Source resolve failed ({exc.code})"
            return StreamSourceResult(
                status="error",
                message=message,
                error_code=error_code,
                raw_output=self._truncate_raw_output(raw_body or str(exc)),
                return_code=exc.code,
            )
        except urllib.error.URLError as exc:
            reason = str(exc.reason)
            lowered = reason.lower()
            error_code = ErrorCode.TIMEOUT if "timed out" in lowered else ErrorCode.SOURCE_RESOLVE_FAILED
            message = "Source resolve timed out" if error_code == ErrorCode.TIMEOUT else "Source resolve failed"
            return StreamSourceResult(
                status="error",
                message=message,
                error_code=error_code,
                raw_output=self._truncate_raw_output(reason),
            )

        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError:
            return StreamSourceResult(
                status="error",
                message="Source resolve returned invalid JSON",
                error_code=ErrorCode.SOURCE_RESOLVE_FAILED,
                raw_output=self._truncate_raw_output(raw_body),
                return_code=status_code,
            )

        room_status = str(data.get("room_status") or "").lower()
        stream_url = str(data.get("hls_source") or "").strip() or None
        hidden_message = str(data.get("hidden_message") or "").strip()
        metadata = {
            "broadcaster_username": data.get("broadcaster_username"),
            "edge_region": data.get("edge_region"),
            "room_status": room_status,
            "source_name": data.get("source_name"),
            "viewer_username": data.get("viewer_username"),
        }

        if room_status == "public":
            if stream_url:
                metadata = metadata | self._extract_source_metadata(stream_url) | {"source_candidates": [stream_url], "source_variant": "resolved"}
            return StreamSourceResult(
                status="public",
                message="Streamer is live",
                stream_url=stream_url,
                metadata=metadata,
                return_code=status_code,
            )
        if room_status in {"offline", "not_online"}:
            return StreamSourceResult("offline", "Streamer offline", metadata=metadata, return_code=status_code)
        if room_status == "away":
            return StreamSourceResult("away", "Streamer offline (away)", metadata=metadata, return_code=status_code)
        if room_status in {"private", "group_show"}:
            return StreamSourceResult("private", "Streamer unavailable (private show)", metadata=metadata, return_code=status_code)
        if room_status == "hidden":
            return StreamSourceResult(
                "hidden",
                hidden_message or "Hidden session in progress",
                metadata=metadata,
                return_code=status_code,
            )
        return StreamSourceResult(
            status=room_status or "error",
            message=self._last_meaningful_line(raw_body),
            error_code=ErrorCode.SOURCE_RESOLVE_FAILED,
            metadata=metadata,
            raw_output=self._truncate_raw_output(raw_body),
            return_code=status_code,
        )

    def probe_command(self, channel: Channel, config: AppConfig, use_cookies: bool, ensure_dependency: EnsureDependency) -> list[str]:
        yt_dlp = ensure_dependency("yt-dlp", config.yt_dlp_path)
        command = [
            yt_dlp,
            "--skip-download",
            "--print",
            "is_live",
            channel.url,
            "--add-header",
            f"Origin: {self.ORIGIN}",
            "--add-header",
            f"Referer: {self._room_referer(channel)}",
            "--user-agent",
            self.USER_AGENT,
        ]
        if use_cookies and self.COOKIE_PATH.exists():
            command[1:1] = ["--cookies", str(self.COOKIE_PATH)]
        return command

    def interpret_probe_result(self, output: str, return_code: int) -> PlatformProbeResult:
        lowered = output.lower()
        if "404" in lowered and "unable to download webpage" in lowered:
            return PlatformProbeResult(False, "Streamer unavailable (room not found)", raw_output=output, return_code=return_code)
        if "room is currently offline" in lowered:
            return PlatformProbeResult(False, "Streamer offline", raw_output=output, return_code=return_code)
        if "performer is currently away" in lowered:
            return PlatformProbeResult(False, "Streamer offline (away)", raw_output=output, return_code=return_code)
        if "private show" in lowered or "private session" in lowered:
            return PlatformProbeResult(False, "Streamer unavailable (private show)", raw_output=output, return_code=return_code)
        if self._is_hidden_show_message(output):
            return PlatformProbeResult(
                False,
                self._last_meaningful_line(output),
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
            return PlatformProbeResult(False, "Stream source unstable (m3u8 404)", None, raw_output=output, return_code=return_code)
        if "#extm3u absent" in lowered:
            return PlatformProbeResult(False, "Stream source unstable (playlist parse failed)", None, raw_output=output, return_code=return_code)
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
        source_url: str,
        ensure_dependency: EnsureDependency,
        format_selector: str,
    ) -> list[str]:
        yt_dlp = ensure_dependency("yt-dlp", config.yt_dlp_path)
        command = [
            yt_dlp,
            "--output",
            str(output_path),
            "--format",
            format_selector,
            "--merge-output-format",
            "mkv",
            "--add-header",
            f"Origin: {self.ORIGIN}",
            "--add-header",
            f"Referer: {self._room_referer(channel)}",
            "--user-agent",
            self.USER_AGENT,
            channel.url,
        ]
        if self.COOKIE_PATH.exists():
            command[1:1] = ["--cookies", str(self.COOKIE_PATH)]
        return command

    def build_record_command_for_source(
        self,
        channel: Channel,
        config: AppConfig,
        output_path: Path,
        source_url: str,
        ensure_dependency: EnsureDependency,
        format_selector: str,
    ) -> list[str]:
        ffmpeg = ensure_dependency("ffmpeg", config.ffmpeg_path)
        record_headers = self._build_record_headers(channel, include_cookies=True)
        rw_timeout = str(max(config.probe_timeout_seconds, 1) * 1_000_000)
        return [
            ffmpeg,
            "-y",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-user_agent",
            self.USER_AGENT,
            "-headers",
            record_headers,
            "-rw_timeout",
            rw_timeout,
            "-i",
            source_url,
            "-c",
            "copy",
            "-f",
            "matroska",
            str(output_path),
        ]

    def map_recording_failure(self, stderr: str, return_code: int) -> RecordingFailure:
        lowered = stderr.lower()
        friendly_error = stderr.strip() or f"Recorder exited with code {return_code}"
        raw_output = self._truncate_raw_output_tail(stderr)
        if "private show" in lowered or "private session" in lowered:
            return RecordingFailure(ErrorCode.RECORDER_EXITED, "Streamer unavailable (private show)", raw_output=raw_output, return_code=return_code)
        if "performer is currently away" in lowered:
            return RecordingFailure(ErrorCode.RECORDER_EXITED, "Streamer offline (away)", raw_output=raw_output, return_code=return_code)
        if (
            "#extm3u absent" in lowered
            or "http error 404" in lowered
            or "server returned 404 not found" in lowered
            or "manifest" in lowered and "404" in lowered
        ):
            return RecordingFailure(
                ErrorCode.SOURCE_URL_EXPIRED,
                "Stream source unstable (m3u8 404)",
                raw_output=raw_output,
                return_code=return_code,
            )
        if "invalid data found when processing input" in lowered:
            return RecordingFailure(
                ErrorCode.PLAYLIST_PARSE_FAILED,
                "Stream source unstable (playlist parse failed)",
                raw_output=raw_output,
                return_code=return_code,
            )
        if "403" in lowered or "401" in lowered:
            return RecordingFailure(
                ErrorCode.SOURCE_URL_EXPIRED,
                "Stream source rejected (403/401)",
                raw_output=raw_output,
                return_code=return_code,
            )
        if "cookie" in lowered:
            return RecordingFailure(ErrorCode.AUTH_OR_COOKIE_FAILED, friendly_error, raw_output=raw_output, return_code=return_code)
        if "timed out" in lowered or "deadline exceeded" in lowered:
            return RecordingFailure(ErrorCode.TIMEOUT, friendly_error, raw_output=raw_output, return_code=return_code)
        return RecordingFailure(ErrorCode.RECORDER_EXITED, friendly_error, raw_output=raw_output, return_code=return_code)
