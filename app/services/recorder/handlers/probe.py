from __future__ import annotations

import subprocess

from app.domain import AppConfig, Channel, ErrorCode
from app.platform import PlatformProbeResult, StreamSourceResult


class ProbeHandler:
    def __init__(self, platforms, service) -> None:
        self.platforms = platforms
        self.service = service

    def _resolver_indicates_public_room(self, result) -> bool:
        metadata = result.metadata or {}
        return str(metadata.get("room_status") or "").lower() == "public"

    def probe(self, channel: Channel, config: AppConfig, resolve_stream_source_fn) -> PlatformProbeResult:
        resolved_source = resolve_stream_source_fn(channel, config)
        if resolved_source.stream_url:
            return PlatformProbeResult(
                True,
                resolved_source.message,
                raw_output=resolved_source.raw_output,
                return_code=resolved_source.return_code,
            )
        if resolved_source.error_code is None:
            return PlatformProbeResult(
                False,
                resolved_source.message,
                raw_output=resolved_source.raw_output,
                return_code=resolved_source.return_code,
            )
        if self._resolver_indicates_public_room(resolved_source):
            return PlatformProbeResult(
                False,
                resolved_source.message,
                resolved_source.error_code,
                raw_output=resolved_source.raw_output,
                return_code=resolved_source.return_code,
            )
        try:
            self.service._ensure_dependency("yt-dlp", config.yt_dlp_path)
        except FileNotFoundError:
            return PlatformProbeResult(
                False,
                resolved_source.message if resolved_source.error_code else "yt-dlp not found",
                resolved_source.error_code or ErrorCode.DEPENDENCY_MISSING,
                raw_output=resolved_source.raw_output or "yt-dlp not found",
                return_code=resolved_source.return_code,
            )
        first_result = self._run_probe_attempt(channel, config, use_cookies=True)
        if first_result.online or first_result.error_code is None:
            return first_result
        if first_result.error_code in {
            ErrorCode.TIMEOUT,
            ErrorCode.AUTH_OR_COOKIE_FAILED,
            ErrorCode.PAGE_FETCH_FAILED,
            ErrorCode.SOURCE_RESOLVE_FAILED,
        }:
            fallback_result = self._run_probe_attempt(channel, config, use_cookies=False)
            if fallback_result.online:
                return fallback_result
            if fallback_result.error_code is None:
                return fallback_result
        return PlatformProbeResult(
            False,
            resolved_source.message,
            resolved_source.error_code,
            raw_output=resolved_source.raw_output,
            return_code=resolved_source.return_code,
        )

    def resolve_stream_source(self, channel: Channel, config: AppConfig) -> StreamSourceResult:
        adapter = self.platforms.get(channel.platform)
        first_result = adapter.resolve_stream_source(channel, config, use_cookies=True)
        if self._resolver_indicates_public_room(first_result) or first_result.stream_url or first_result.error_code is None:
            return first_result
        if first_result.error_code in {ErrorCode.TIMEOUT, ErrorCode.AUTH_OR_COOKIE_FAILED, ErrorCode.SOURCE_RESOLVE_FAILED}:
            fallback_result = adapter.resolve_stream_source(channel, config, use_cookies=False)
            if fallback_result.stream_url or fallback_result.error_code is None:
                return fallback_result
        return first_result

    def _run_probe_attempt(self, channel: Channel, config: AppConfig, use_cookies: bool) -> StreamSourceResult:
        adapter = self.platforms.get(channel.platform)
        command = adapter.probe_command(
            channel,
            config,
            use_cookies=use_cookies,
            ensure_dependency=self.service._ensure_dependency,
        )
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=config.probe_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            suffix = " with cookies" if use_cookies else " without cookies"
            return PlatformProbeResult(
                False,
                f"Probe timed out{suffix}",
                ErrorCode.TIMEOUT,
                raw_output=f"Probe timed out after {config.probe_timeout_seconds}s{suffix}",
            )

        output = (result.stdout + "\n" + result.stderr).strip()
        cleaned_output = self._sanitize_yt_dlp_message(output)
        return adapter.interpret_probe_result(cleaned_output or output, result.returncode)

    def _sanitize_yt_dlp_message(self, output: str) -> str:
        lines = []
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if "The extractor is attempting impersonation" in stripped:
                continue
            if stripped.startswith("[debug]"):
                continue
            lines.append(stripped)
        if not lines:
            return output.strip()
        return "\n".join(lines)
