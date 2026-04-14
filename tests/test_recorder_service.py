from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.domain import AppConfig, Channel, Platform
from app.services.recorder.service import RecorderService


class RecorderServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MagicMock()
        self.channel_service = MagicMock()
        self.platforms = MagicMock()
        self.service = RecorderService(self.store, self.channel_service, self.platforms)
        self.config = AppConfig(source_retry_max_attempts=1)
        self.store.load_config.return_value = self.config
        self.channel = Channel(
            id="chan-1",
            username="alice",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/alice",
            created_at=1,
        )

    def test_acquire_resolved_source_for_room_page_platform_uses_single_api_check(self) -> None:
        self.platforms.get.return_value.record_uses_resolved_source.return_value = False
        self.service.resolve_stream_source = MagicMock(return_value=MagicMock(
            stream_url="https://edge.example/live.m3u8",
            message="Streamer is live",
            error_code=None,
            raw_output=None,
            return_code=200,
            metadata={"room_status": "public"},
        ))

        resolved = self.service.acquire_resolved_source(self.channel, self.config, session_id="sess-1")

        self.assertEqual(resolved.room_status, "public")
        self.assertEqual(resolved.stream_url, "https://edge.example/live.m3u8")
        self.service.resolve_stream_source.assert_called_once()

    def test_build_record_command_prefers_muxed_stream_before_split_streams(self) -> None:
        adapter = MagicMock()
        adapter.build_record_command.return_value = ["yt-dlp", "https://example.com"]
        self.platforms.get.return_value = adapter

        command = self.service.build_record_command(
            self.channel,
            self.config,
            Path("/tmp/capture.mkv"),
            "https://chaturbate.com/alice",
        )

        self.assertEqual(command, ["yt-dlp", "https://example.com"])
        adapter.build_record_command.assert_called_once_with(
            channel=self.channel,
            config=self.config,
            output_path=Path("/tmp/capture.mkv"),
            source_url="https://chaturbate.com/alice",
            ensure_dependency=self.service._ensure_dependency,
            format_selector="best/bestvideo+bestaudio/best",
        )

    def test_build_convert_command_uses_async_audio_resample_and_aac_output(self) -> None:
        self.service._ensure_dependency = MagicMock(return_value="ffmpeg")

        command = self.service.build_convert_command(
            Path("/tmp/capture.mkv"),
            Path("/tmp/capture.mp4"),
        )

        self.assertEqual(
            command,
            [
                "ffmpeg", "-fflags", "+genpts",
                "-i", "/tmp/capture.mkv",
                "-c:v", "copy",
                "-af", "aresample=async=1",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                "-movflags", "faststart",
                "/tmp/capture.mp4", "-y",
            ],
        )
        self.service._ensure_dependency.assert_called_once_with("ffmpeg", self.config.ffmpeg_path)

if __name__ == "__main__":
    unittest.main()
