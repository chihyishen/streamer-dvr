from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

from app.domain import Channel, ErrorCode, Platform, Status
from app.platform import PlatformProbeResult
from app.services.scheduler.probe import SchedulerProbeMixin


class _SchedulerUnderTest(SchedulerProbeMixin):
    def __init__(self) -> None:
        self._probe_slots = threading.Semaphore(1)
        self._active_processes: dict[str, object] = {}
        self._last_probe_started_at = 0.0
        self.store = MagicMock()
        self.channel_service = MagicMock()
        self.recorder = MagicMock()
        self._start_recording = MagicMock()


class SchedulerProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.channel = Channel(
            id="chan-1",
            username="alice",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/alice",
            created_at=1,
        )

    def test_check_channel_treats_hidden_show_as_idle_not_error(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.store.load_config.return_value = MagicMock(probe_rate_limit_seconds=0)
        scheduler.recorder.probe.return_value = PlatformProbeResult(
            False,
            "Secret Show in progress TICKET SHOW Hidden Cam",
            ErrorCode.AUTH_OR_COOKIE_FAILED,
            raw_output="Secret Show in progress TICKET SHOW Hidden Cam",
            return_code=200,
        )

        scheduler._check_channel(self.channel.id)

        scheduler.channel_service.update_status.assert_any_call(
            self.channel.id,
            status=Status.IDLE,
            last_error=None,
            next_check_at=unittest.mock.ANY,
        )
        scheduler.store.log_error.assert_not_called()

    def test_check_channel_uses_longer_backoff_for_source_unstable(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.store.load_config.return_value = MagicMock(probe_rate_limit_seconds=0)
        scheduler.recorder.probe.return_value = PlatformProbeResult(
            False,
            "Validated stream source returned 404",
            ErrorCode.SOURCE_URL_EXPIRED,
            raw_output="https://edge.example/playlist.m3u8",
            return_code=404,
        )

        with patch("app.services.scheduler.probe.compute_next_check_at", side_effect=["checking-at", "retry-at"]) as next_check_mock:
            scheduler._check_channel(self.channel.id)

        next_check_mock.assert_any_call(self.channel.id, self.channel.poll_interval_seconds)
        next_check_mock.assert_any_call(self.channel.id, self.channel.poll_interval_seconds, 900)
        scheduler.channel_service.update_status.assert_any_call(
            self.channel.id,
            status=Status.ERROR,
            last_error="Validated stream source returned 404",
            next_check_at="retry-at",
        )

    def test_check_channel_starts_recording_when_api_reports_public(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.store.load_config.return_value = MagicMock(probe_rate_limit_seconds=0)
        scheduler.recorder = MagicMock()
        scheduler.recorder.acquire_resolved_source.return_value = MagicMock(
            stream_url=None,
            room_status="public",
            message="Streamer is live",
        )
        scheduler.sessions = MagicMock()
        scheduler.sessions.open.return_value = MagicMock(id="sess-1")

        scheduler._check_channel(self.channel.id)

        scheduler._start_recording.assert_called_once()
        scheduler.sessions.fail.assert_not_called()


if __name__ == "__main__":
    unittest.main()
