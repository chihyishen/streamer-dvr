from __future__ import annotations

import subprocess

from ...domain import AppConfig, Channel, ErrorCode
from ...platform import PlatformProbeResult


class RecorderProbeMixin:
    def probe(self, channel: Channel, config: AppConfig) -> PlatformProbeResult:
        try:
            self._ensure_dependency("yt-dlp", config.yt_dlp_path)
        except FileNotFoundError:
            return PlatformProbeResult(False, "yt-dlp not found", ErrorCode.DEPENDENCY_MISSING, raw_output="yt-dlp not found")
        first_result = self._run_probe_attempt(channel, config, use_cookies=True)
        if first_result.online:
            return first_result
        if first_result.error_code in {ErrorCode.TIMEOUT, ErrorCode.AUTH_OR_COOKIE_FAILED}:
            fallback_result = self._run_probe_attempt(channel, config, use_cookies=False)
            if fallback_result.online:
                return fallback_result
            if fallback_result.error_code is None:
                return fallback_result
        return first_result

    def _run_probe_attempt(self, channel: Channel, config: AppConfig, use_cookies: bool) -> PlatformProbeResult:
        adapter = self.platforms.get(channel.platform)
        command = adapter.probe_command(channel, config, use_cookies=use_cookies, ensure_dependency=self._ensure_dependency)
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
