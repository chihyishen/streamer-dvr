from __future__ import annotations

import json
import tempfile
import urllib.error
import unittest
from pathlib import Path
from unittest.mock import patch

from app.domain import AppConfig, Channel, ErrorCode, Platform
from app.platform import ChaturbatePlatform


class _FakeResponse:
    def __init__(self, payload: dict[str, object] | str, status: int = 200) -> None:
        self.status = status
        if isinstance(payload, str):
            self._payload = payload.encode("utf-8")
        else:
            self._payload = json.dumps(payload).encode("utf-8")

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            return self._payload
        return self._payload[:size]

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def close(self) -> None:
        return None


class ChaturbatePlatformTests(unittest.TestCase):
    def setUp(self) -> None:
        self.platform = ChaturbatePlatform()
        self.config = AppConfig()
        self.channel = Channel(
            id="chan-1",
            username="sugarpoppyxo",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/sugarpoppyxo",
            created_at=1,
        )

    def test_resolve_stream_source_uses_hls_source_for_public_room(self) -> None:
        payload = {
            "room_status": "public",
            "hls_source": "https://edge15-sin.live.mmcdn.com/live-edge/example/playlist.m3u8",
            "edge_region": "SIN",
            "viewer_username": "stu050514",
            "broadcaster_username": "sugarpoppyxo",
            "source_name": "di",
        }
        with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
            result = self.platform.resolve_stream_source(self.channel, self.config, use_cookies=False)

        self.assertEqual(result.status, "public")
        self.assertEqual(result.stream_url, payload["hls_source"])
        self.assertEqual(result.metadata["edge_region"], "SIN")
        self.assertEqual(result.metadata["source_path_tail"], "playlist.m3u8")
        self.assertIsNone(result.raw_output)

    def test_resolve_stream_source_maps_offline_room(self) -> None:
        payload = {
            "room_status": "offline",
            "hls_source": "",
            "broadcaster_username": "ash_and_e",
            "edge_region": "",
            "source_name": "di",
            "viewer_username": "stu050514",
        }
        with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
            result = self.platform.resolve_stream_source(self.channel, self.config, use_cookies=False)

        self.assertEqual(result.status, "offline")
        self.assertEqual(result.message, "Streamer offline")
        self.assertIsNone(result.stream_url)

    def test_resolve_stream_source_rejects_public_room_without_hls_source(self) -> None:
        payload = {"room_status": "public", "hls_source": ""}
        with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
            result = self.platform.resolve_stream_source(self.channel, self.config, use_cookies=False)

        self.assertEqual(result.status, "public")
        self.assertEqual(result.message, "Streamer is live")
        self.assertIsNone(result.error_code)

    def test_resolve_stream_source_does_not_validate_playlist_before_recording(self) -> None:
        payload = {
            "room_status": "public",
            "hls_source": "https://edge15-sin.live.mmcdn.com/live-edge/example/playlist.m3u8?t=%7B%22expire%22%3A1774541135%7D",
            "edge_region": "SIN",
            "viewer_username": "stu050514",
            "broadcaster_username": "sugarpoppyxo",
            "source_name": "di",
        }
        with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
            result = self.platform.resolve_stream_source(self.channel, self.config, use_cookies=False)

        self.assertEqual(result.status, "public")
        self.assertEqual(result.message, "Streamer is live")
        self.assertEqual(result.metadata["source_expire"], 1774541135)
        self.assertEqual(result.stream_url, payload["hls_source"])

    def test_resolve_stream_source_keeps_reported_hls_source_without_candidate_swapping(self) -> None:
        payload = {
            "room_status": "public",
            "hls_source": "https://edge5-sin.live.mmcdn.com/v1/edge/streams/origin.hannah_lourens.abc/llhls.m3u8?token=xyz",
            "edge_region": "SIN",
            "viewer_username": "stu050514",
            "broadcaster_username": "hannah_lourens",
            "source_name": "di",
        }
        with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
            result = self.platform.resolve_stream_source(self.channel, self.config, use_cookies=False)

        self.assertEqual(result.status, "public")
        self.assertEqual(result.stream_url, payload["hls_source"])
        self.assertEqual(result.metadata["source_candidates"], [payload["hls_source"]])
        self.assertEqual(result.metadata["source_variant"], "resolved")

    def test_resolve_stream_source_treats_hidden_show_as_unavailable_not_auth_error(self) -> None:
        payload = {
            "room_status": "hidden",
            "hidden_message": "Secret Show in progress TICKET SHOW Hidden Cam",
            "broadcaster_username": "sugarpoppyxo",
            "edge_region": "SIN",
            "source_name": "di",
            "viewer_username": "stu050514",
        }
        with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
            result = self.platform.resolve_stream_source(self.channel, self.config, use_cookies=False)

        self.assertEqual(result.status, "hidden")
        self.assertEqual(result.message, "Secret Show in progress TICKET SHOW Hidden Cam")
        self.assertIsNone(result.error_code)
        self.assertIsNone(result.stream_url)

    def test_resolve_stream_source_treats_password_required_as_unavailable_not_auth_error(self) -> None:
        payload = {
            "status": 403,
            "detail": "This room requires a password.",
            "code": "password-required",
            "ts_context": None,
        }
        http_error = urllib.error.HTTPError(
            self.platform.SOURCE_ENDPOINT.format(username=self.channel.username),
            403,
            "Forbidden",
            hdrs=None,
            fp=_FakeResponse(payload),
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            result = self.platform.resolve_stream_source(self.channel, self.config, use_cookies=False)

        self.assertEqual(result.status, "private")
        self.assertEqual(result.message, "Streamer unavailable (password protected)")
        self.assertIsNone(result.error_code)
        self.assertIsNone(result.stream_url)

    def test_resolve_stream_source_treats_missing_room_404_as_unavailable(self) -> None:
        html_404 = "<html><head><title>404 Not Found</title></head><body>Page not found</body></html>"
        http_error = urllib.error.HTTPError(
            self.platform.SOURCE_ENDPOINT.format(username=self.channel.username),
            404,
            "Not Found",
            hdrs=None,
            fp=_FakeResponse(html_404),
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            result = self.platform.resolve_stream_source(self.channel, self.config, use_cookies=False)

        self.assertEqual(result.status, "offline")
        self.assertEqual(result.message, "Streamer unavailable (room not found)")
        self.assertIsNone(result.error_code)

    def test_build_record_command_uses_yt_dlp_defaults_and_consistent_headers(self) -> None:
        self.assertTrue(self.platform.record_uses_resolved_source())
        with tempfile.TemporaryDirectory() as tmpdir:
            cookie_path = Path(tmpdir) / "streamer_cookies.txt"
            cookie_path.write_text(
                "# Netscape HTTP Cookie File\n.chaturbate.com\tTRUE\t/\tTRUE\t0\tsessionid\tabc123\n",
                encoding="utf-8",
            )
            with patch.object(self.platform, "COOKIE_PATH", cookie_path):
                command = self.platform.build_record_command(
                    channel=self.channel,
                    config=self.config,
                    output_path=Path("recordings/test.mkv"),
                    source_url="https://edge15-sin.live.mmcdn.com/live-edge/example/playlist.m3u8",
                    ensure_dependency=lambda *_: "yt-dlp",
                    format_selector="best",
                )

        self.assertEqual(command[0], "yt-dlp")
        self.assertIn("https://chaturbate.com/sugarpoppyxo", command)
        self.assertIn("--cookies", command)
        self.assertIn(str(cookie_path), command)
        self.assertNotIn("--live-from-start", command)
        self.assertIn("--merge-output-format", command)
        self.assertIn("mkv", command)
        self.assertNotIn("--hls-use-mpegts", command)
        self.assertNotIn("--downloader", command)
        self.assertNotIn("--downloader-args", command)
        self.assertIn("Origin: https://chaturbate.com", command)
        self.assertIn("Referer: https://chaturbate.com/sugarpoppyxo/", command)

    def test_build_record_command_ignores_resolved_source_url_and_records_room_page(self) -> None:
        command = self.platform.build_record_command(
            channel=self.channel,
            config=self.config,
            output_path=Path("recordings/test.mkv"),
            source_url="https://edge5-sin.live.mmcdn.com/v1/edge/streams/origin.hannah_lourens.abc/llhls.m3u8?token=xyz",
            ensure_dependency=lambda *_: "yt-dlp",
            format_selector="best",
        )

        self.assertIn("https://chaturbate.com/sugarpoppyxo", command)
        self.assertNotIn("https://edge5-sin.live.mmcdn.com/v1/edge/streams/origin.hannah_lourens.abc/llhls.m3u8?token=xyz", command)

    def test_build_record_command_for_source_uses_ffmpeg_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cookie_path = Path(tmpdir) / "streamer_cookies.txt"
            cookie_path.write_text(
                "# Netscape HTTP Cookie File\n.chaturbate.com\tTRUE\t/\tTRUE\t0\tsessionid\tabc123\n",
                encoding="utf-8",
            )
            with patch.object(self.platform, "COOKIE_PATH", cookie_path):
                command = self.platform.build_record_command_for_source(
                    channel=self.channel,
                    config=self.config,
                    output_path=Path("recordings/direct.mkv"),
                    source_url="https://edge.example/live/playlist.m3u8",
                    ensure_dependency=lambda binary, _path=None: binary,
                    format_selector="best",
                )

        self.assertEqual(command[0], "ffmpeg")
        self.assertIn("-headers", command)
        self.assertIn("-rw_timeout", command)
        self.assertIn("-i", command)
        self.assertIn("https://edge.example/live/playlist.m3u8", command)
        self.assertNotIn("https://chaturbate.com/sugarpoppyxo", command)

    def test_map_recording_failure_truncates_to_tail_summary(self) -> None:
        noisy_lines = [f"frame={idx}" for idx in range(120)]
        noisy_lines.append("HTTP error 403 Forbidden")
        noisy_lines.append("Failed to reload playlist 0")
        stderr = "\n".join(noisy_lines)

        result = self.platform.map_recording_failure(stderr, 1)

        self.assertEqual(result.error_code, ErrorCode.SOURCE_URL_EXPIRED)
        self.assertIsNotNone(result.raw_output)
        assert result.raw_output is not None
        self.assertNotIn("frame=0", result.raw_output)
        self.assertIn("HTTP error 403 Forbidden", result.raw_output)
        self.assertIn("Failed to reload playlist 0", result.raw_output)
        self.assertLessEqual(len(result.raw_output), self.platform.RAW_OUTPUT_LIMIT + len("[truncated]..."))


if __name__ == "__main__":
    unittest.main()
