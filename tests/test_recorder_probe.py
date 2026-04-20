from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.domain import AppConfig, Channel, ErrorCode, Platform
from app.platform import PlatformProbeResult, StreamSourceResult
from app.services.recorder.handlers.probe import ProbeHandler


class _RecorderUnderTest:
    def __init__(self) -> None:
        self.platforms = MagicMock()
        self.service = MagicMock()
        self.service._ensure_dependency = MagicMock(side_effect=lambda binary, _path=None: binary)
        self.handler = ProbeHandler(self.platforms, self.service)

    def probe(self, channel: Channel, config: AppConfig) -> any:
        return self.handler.probe(channel, config, self.resolve_stream_source)

    def resolve_stream_source(self, channel: Channel, config: AppConfig) -> any:
        return self.handler.resolve_stream_source(channel, config)

    def _resolver_indicates_public_room(self, result) -> bool:
        return self.handler._resolver_indicates_public_room(result)

    def _run_probe_attempt(self, channel: Channel, config: AppConfig, use_cookies: bool) -> any:
        return self.handler._run_probe_attempt(channel, config, use_cookies)


class RecorderProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AppConfig()
        self.channel = Channel(
            id="chan-1",
            username="alice",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/alice",
            created_at=1,
        )

    def test_probe_short_circuits_when_resolver_returns_stream_url(self) -> None:
        recorder = _RecorderUnderTest()
        recorder.resolve_stream_source = MagicMock(
            return_value=StreamSourceResult(status="public", message="Streamer is live", stream_url="https://cdn.example/live.m3u8")
        )
        recorder.handler._run_probe_attempt = MagicMock()

        result = recorder.probe(self.channel, self.config)

        self.assertTrue(result.online)
        recorder.handler._run_probe_attempt.assert_not_called()

    def test_resolve_stream_source_retries_without_cookies_after_auth_failure(self) -> None:
        recorder = _RecorderUnderTest()
        adapter = recorder.platforms.get.return_value
        adapter.resolve_stream_source.side_effect = [
            StreamSourceResult(status="error", message="Auth/cookie failure", error_code=ErrorCode.AUTH_OR_COOKIE_FAILED),
            StreamSourceResult(status="public", message="Streamer is live", stream_url="https://cdn.example/live.m3u8"),
        ]

        result = recorder.resolve_stream_source(self.channel, self.config)

        self.assertEqual(result.stream_url, "https://cdn.example/live.m3u8")
        self.assertEqual(adapter.resolve_stream_source.call_count, 2)

    def test_probe_falls_back_to_yt_dlp_when_resolver_errors(self) -> None:
        recorder = _RecorderUnderTest()
        recorder.resolve_stream_source = MagicMock(
            return_value=StreamSourceResult(
                status="error",
                message="Source resolve failed",
                error_code=ErrorCode.SOURCE_RESOLVE_FAILED,
            )
        )
        recorder.handler._run_probe_attempt = MagicMock(return_value=PlatformProbeResult(False, "Streamer offline"))

        result = recorder.probe(self.channel, self.config)

        self.assertFalse(result.online)
        self.assertIsNone(result.error_code)
        self.assertEqual(recorder.handler._run_probe_attempt.call_count, 1)

    def test_probe_does_not_fallback_to_yt_dlp_when_resolver_says_public_but_source_failed(self) -> None:
        recorder = _RecorderUnderTest()
        recorder.resolve_stream_source = MagicMock(
            return_value=StreamSourceResult(
                status="error",
                message="Validated stream source returned 404",
                error_code=ErrorCode.SOURCE_URL_EXPIRED,
                metadata={"room_status": "public"},
            )
        )
        recorder.handler._run_probe_attempt = MagicMock(return_value=PlatformProbeResult(False, "Streamer offline"))

        result = recorder.probe(self.channel, self.config)

        self.assertFalse(result.online)
        self.assertEqual(result.error_code, ErrorCode.SOURCE_URL_EXPIRED)
        self.assertEqual(result.message, "Validated stream source returned 404")
        recorder.handler._run_probe_attempt.assert_not_called()


    def test_resolve_stream_source_does_not_retry_without_cookies_when_room_is_public(self) -> None:
        recorder = _RecorderUnderTest()
        adapter = recorder.platforms.get.return_value
        adapter.resolve_stream_source.return_value = StreamSourceResult(
            status="error",
            message="Validated stream source returned 403",
            error_code=ErrorCode.SOURCE_URL_EXPIRED,
            metadata={"room_status": "public"},
        )

        result = recorder.resolve_stream_source(self.channel, self.config)

        self.assertEqual(result.error_code, ErrorCode.SOURCE_URL_EXPIRED)
        adapter.resolve_stream_source.assert_called_once_with(self.channel, self.config, use_cookies=True)

    def test_probe_private_show_is_not_treated_as_error(self) -> None:
        recorder = _RecorderUnderTest()
        recorder.resolve_stream_source = MagicMock(
            return_value=StreamSourceResult(
                status="private",
                message="Streamer unavailable (private show)",
                error_code=None,
                metadata={"room_status": "private"},
            )
        )

        result = recorder.probe(self.channel, self.config)

        self.assertFalse(result.online)
        self.assertIsNone(result.error_code)
        self.assertEqual(result.message, "Streamer unavailable (private show)")


if __name__ == "__main__":
    unittest.main()
