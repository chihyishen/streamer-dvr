from __future__ import annotations

import io
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from app.domain import AppConfig, Channel, ErrorCode, Platform, Status
from app.services.session_core import FailureCategory, RecordingPhase
from app.services.scheduler.capture import SchedulerCaptureMixin


class _SchedulerUnderTest(SchedulerCaptureMixin):
    def __init__(self) -> None:
        self._record_lock = threading.RLock()
        self._active_processes: dict[str, object] = {}
        self.store = MagicMock()
        self.channel_service = MagicMock()
        self.recorder = MagicMock()
        self._start_recording = MagicMock()


class SchedulerCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.channel = Channel(
            id="chan-1",
            username="alice",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/alice",
            created_at=1,
        )

    def test_wait_for_recording_retries_with_backoff_until_source_refresh_succeeds(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler._active_processes[self.channel.id] = object()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.store.load_config.return_value = AppConfig(source_retry_max_attempts=5)
        scheduler.recorder.should_refresh_stream_source.return_value = True
        scheduler.recorder.compute_source_retry_delay.side_effect = [1.0, 2.0]
        scheduler.recorder.resolve_stream_source.side_effect = [
            MagicMock(stream_url=None, message="Source resolve failed", error_code=ErrorCode.SOURCE_RESOLVE_FAILED, raw_output="{}", return_code=502),
            MagicMock(
                stream_url="https://cdn.example/refreshed.m3u8",
                message="Streamer is live",
                raw_output=None,
                return_code=200,
                metadata={"source_candidates": ["https://cdn.example/refreshed.m3u8"]},
            ),
        ]
        scheduler.recorder.platforms.get.return_value.map_recording_failure.return_value = MagicMock(
            message="Stream source unstable (m3u8 404)",
            error_code=MagicMock(value="SOURCE_URL_EXPIRED"),
            raw_output="404",
            return_code=1,
        )
        process = MagicMock()
        process.stderr = io.StringIO("ERROR: failed to download m3u8 information: HTTP Error 404")
        process.wait.return_value = 1

        with TemporaryDirectory() as tmpdir, patch("app.services.scheduler.capture.time.sleep") as sleep_mock:
            source_path = Path(tmpdir) / "capture.mkv"
            mp4_path = Path(tmpdir) / "capture.mp4"
            scheduler._wait_for_recording(
                self.channel.id,
                process,
                source_path,
                mp4_path,
                ["https://cdn.example/primary.m3u8"],
                0,
                0,
            )

        scheduler._start_recording.assert_called_once_with(
            self.channel.id,
            prepared_paths=(source_path, mp4_path),
            source_url="https://cdn.example/refreshed.m3u8",
            source_candidates=["https://cdn.example/refreshed.m3u8"],
            source_index=0,
            retry_attempt=2,
        )
        self.assertEqual(scheduler.recorder.resolve_stream_source.call_count, 2)
        sleep_mock.assert_any_call(1.0)
        sleep_mock.assert_any_call(2.0)

    def test_wait_for_recording_marks_refresh_exhausted_when_resolve_fails(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler._active_processes[self.channel.id] = object()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.store.load_config.return_value = AppConfig(source_retry_max_attempts=3)
        scheduler.recorder.should_refresh_stream_source.return_value = True
        scheduler.recorder.compute_source_retry_delay.side_effect = [1.0, 2.0, 4.0]
        scheduler.recorder.resolve_stream_source.side_effect = [
            MagicMock(stream_url=None, message="Source resolve failed", error_code=ErrorCode.SOURCE_RESOLVE_FAILED, raw_output="{}", return_code=502),
            MagicMock(stream_url=None, message="Source resolve failed", error_code=ErrorCode.SOURCE_RESOLVE_FAILED, raw_output="{}", return_code=502),
            MagicMock(stream_url=None, message="Source resolve failed", error_code=ErrorCode.SOURCE_RESOLVE_FAILED, raw_output="{}", return_code=502),
        ]
        scheduler.recorder.platforms.get.return_value.map_recording_failure.return_value = MagicMock(
            message="Stream source unstable (playlist parse failed)",
            error_code=MagicMock(value="SOURCE_URL_EXPIRED"),
            raw_output="parse failed",
            return_code=1,
        )
        process = MagicMock()
        process.stderr = io.StringIO("ERROR: #EXTM3U absent")
        process.wait.return_value = 1

        with TemporaryDirectory() as tmpdir, patch("app.services.scheduler.capture.time.sleep") as sleep_mock:
            source_path = Path(tmpdir) / "capture.mkv"
            mp4_path = Path(tmpdir) / "capture.mp4"
            scheduler._wait_for_recording(
                self.channel.id,
                process,
                source_path,
                mp4_path,
                ["https://cdn.example/primary.m3u8"],
                0,
                0,
            )

        scheduler.channel_service.update_status.assert_any_call(
            self.channel.id,
            status=Status.ERROR,
            active_pid=None,
            last_error="Stream source refresh exhausted",
        )
        scheduler.store.log_error.assert_any_call(
            "SOURCE_URL_EXPIRED",
            "Stream source refresh exhausted",
            self.channel.id,
            raw_output="parse failed",
            return_code=1,
            retry_attempt=3,
        )
        self.assertEqual(sleep_mock.call_count, 3)

    def test_start_recording_retries_source_resolution_before_launching_ffmpeg(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.store.load_config.return_value = AppConfig(source_retry_max_attempts=2)
        scheduler.recorder.compute_paths.return_value = (Path("/tmp/capture.mkv"), Path("/tmp/capture.mp4"))
        scheduler.recorder.compute_source_retry_delay.side_effect = [1.0, 2.0]
        scheduler.recorder.resolve_stream_source.side_effect = [
            MagicMock(
                stream_url=None,
                message="Validated stream source returned 404",
                error_code=ErrorCode.SOURCE_URL_EXPIRED,
                raw_output="https://edge.example/playlist.m3u8",
                return_code=404,
                metadata={"edge_region": "SIN", "source_expire": 1774572347, "source_path_tail": "playlist.m3u8"},
            ),
            MagicMock(
                stream_url="https://edge.example/refreshed.m3u8",
                message="Streamer is live",
                error_code=None,
                raw_output=None,
                return_code=200,
                metadata={
                    "edge_region": "SIN",
                    "source_expire": 1774572355,
                    "source_path_tail": "playlist.m3u8",
                    "source_candidates": ["https://edge.example/refreshed.m3u8"],
                },
            ),
        ]
        scheduler.recorder.build_record_command.return_value = ["ffmpeg", "-i", "https://edge.example/refreshed.m3u8"]

        process = MagicMock()
        process.pid = 4321
        thread_mock = MagicMock()
        with patch("app.services.scheduler.capture.time.sleep") as sleep_mock, patch("subprocess.Popen", return_value=process), patch("threading.Thread", return_value=thread_mock):
            SchedulerCaptureMixin._start_recording(scheduler, self.channel.id)

        sleep_mock.assert_called_once_with(1.0)
        scheduler.recorder.resolve_stream_source.assert_called()
        scheduler.recorder.build_record_command.assert_called_once()
        thread_mock.start.assert_called_once()
        scheduler.store.log_error.assert_called_once_with(
            "SOURCE_URL_EXPIRED",
            "Validated stream source returned 404",
            self.channel.id,
            raw_output="https://edge.example/playlist.m3u8",
            return_code=404,
            retry_attempt=0,
            edge_region="SIN",
            source_expire=1774572347,
            source_path_tail="playlist.m3u8",
        )

    def test_start_recording_skips_source_resolution_for_direct_record_platform(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.store.load_config.return_value = AppConfig()
        scheduler.recorder.compute_paths.return_value = (Path("/tmp/capture.mkv"), Path("/tmp/capture.mp4"))
        scheduler.recorder.platforms.get.return_value.record_uses_resolved_source.return_value = False
        scheduler.recorder.build_record_command.return_value = ["yt-dlp", "https://chaturbate.com/alice"]

        process = MagicMock()
        process.pid = 999
        thread_mock = MagicMock()
        with patch("subprocess.Popen", return_value=process), patch("threading.Thread", return_value=thread_mock):
            SchedulerCaptureMixin._start_recording(scheduler, self.channel.id)

        scheduler.recorder.resolve_stream_source.assert_not_called()
        scheduler.recorder.build_record_command.assert_called_once_with(
            self.channel,
            scheduler.store.load_config.return_value,
            Path("/tmp/capture.mkv"),
            "https://chaturbate.com/alice",
        )
        thread_mock.start.assert_called_once()

    def test_start_recording_session_uses_channel_url_when_platform_prefers_room_page(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.store.load_config.return_value = AppConfig()
        scheduler.recorder.compute_paths.return_value = (Path("/tmp/capture.mkv"), Path("/tmp/capture.mp4"))
        scheduler.recorder.platforms.get.return_value.record_uses_resolved_source.return_value = False
        scheduler.recorder.build_record_command.return_value = ["yt-dlp", "https://chaturbate.com/alice"]
        scheduler._attach_session_source = MagicMock()
        scheduler._transition_session = MagicMock()
        scheduler._wait_for_recording = MagicMock()

        resolved_source = MagicMock(stream_url="https://edge.example/live.m3u8", room_status="public")
        session = MagicMock(id="sess-1")
        process = MagicMock()
        process.pid = 1234
        thread_mock = MagicMock()

        with patch("subprocess.Popen", return_value=process), patch("threading.Thread", return_value=thread_mock):
            SchedulerCaptureMixin._start_recording_session(
                scheduler,
                self.channel.id,
                session=session,
                resolved_source=resolved_source,
            )

        scheduler.recorder.build_record_command.assert_called_once_with(
            self.channel,
            scheduler.store.load_config.return_value,
            Path("/tmp/capture.mkv"),
            "https://chaturbate.com/alice",
        )
        scheduler.recorder.build_resolved_record_command.assert_not_called()
        scheduler._transition_session.assert_called_once()
        transition_kwargs = scheduler._transition_session.call_args.kwargs
        self.assertEqual(transition_kwargs["source_url"], "https://chaturbate.com/alice")
        thread_mock.start.assert_called_once()

    def test_start_recording_session_uses_channel_url_without_source_resolution_for_room_page_platform(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.store.load_config.return_value = AppConfig()
        scheduler.recorder.compute_paths.return_value = (Path("/tmp/capture.mkv"), Path("/tmp/capture.mp4"))
        scheduler.recorder.platforms.get.return_value.record_uses_resolved_source.return_value = False
        scheduler.recorder.build_record_command.return_value = ["yt-dlp", "https://chaturbate.com/alice"]
        scheduler._attach_session_source = MagicMock()
        scheduler._transition_session = MagicMock()
        scheduler._wait_for_recording = MagicMock()

        session = MagicMock(id="sess-1")
        process = MagicMock()
        process.pid = 1234
        thread_mock = MagicMock()

        with patch("subprocess.Popen", return_value=process), patch("threading.Thread", return_value=thread_mock):
            SchedulerCaptureMixin._start_recording_session(
                scheduler,
                self.channel.id,
                session=session,
            )

        scheduler.recorder.build_record_command.assert_called_once_with(
            self.channel,
            scheduler.store.load_config.return_value,
            Path("/tmp/capture.mkv"),
            "https://chaturbate.com/alice",
        )
        self.assertEqual(scheduler._transition_session.call_count, 1)
        transition_kwargs = scheduler._transition_session.call_args.kwargs
        self.assertEqual(transition_kwargs["source_url"], "https://chaturbate.com/alice")
        thread_mock.start.assert_called_once()

    def test_start_recording_treats_hidden_show_resolution_as_unavailable_not_error(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.store.load_config.return_value = AppConfig(source_retry_max_attempts=2)
        scheduler.recorder.compute_paths.return_value = (Path("/tmp/capture.mkv"), Path("/tmp/capture.mp4"))
        scheduler.recorder.resolve_stream_source.return_value = MagicMock(
            stream_url=None,
            message="Secret Show in progress TICKET SHOW Hidden Cam",
            error_code=None,
            raw_output="Secret Show in progress TICKET SHOW Hidden Cam",
            return_code=200,
            metadata={"room_status": "hidden"},
        )

        SchedulerCaptureMixin._start_recording(scheduler, self.channel.id)

        scheduler.channel_service.update_status.assert_any_call(
            self.channel.id,
            status=Status.IDLE,
            last_error=None,
        )
        scheduler.store.log_info.assert_called_once_with(
            "source_resolve_skipped",
            "Secret Show in progress TICKET SHOW Hidden Cam",
            self.channel.id,
            raw_output="Secret Show in progress TICKET SHOW Hidden Cam",
            return_code=200,
            edge_region=None,
            source_expire=None,
            source_path_tail=None,
        )
        scheduler.store.log_error.assert_not_called()

    def test_wait_for_recording_tries_alternate_source_candidate_before_re_resolve(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler._active_processes[self.channel.id] = object()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.recorder.should_refresh_stream_source.return_value = True
        scheduler.recorder.platforms.get.return_value.map_recording_failure.return_value = MagicMock(
            message="Stream source rejected (403/401)",
            error_code=MagicMock(value="SOURCE_URL_EXPIRED"),
            raw_output="403",
            return_code=1,
        )
        process = MagicMock()
        process.stderr = io.StringIO("HTTP error 403 Forbidden")
        process.wait.return_value = 1

        with TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "capture.mkv"
            mp4_path = Path(tmpdir) / "capture.mp4"
            scheduler._wait_for_recording(
                self.channel.id,
                process,
                source_path,
                mp4_path,
                [
                    "https://edge.example/llhls.m3u8",
                    "https://edge.example/playlist.m3u8",
                ],
                0,
                0,
            )

        scheduler._start_recording.assert_called_once_with(
            self.channel.id,
            prepared_paths=(source_path, mp4_path),
            source_url="https://edge.example/playlist.m3u8",
            source_candidates=[
                "https://edge.example/llhls.m3u8",
                "https://edge.example/playlist.m3u8",
            ],
            source_index=1,
            retry_attempt=0,
        )

    def test_wait_for_recording_treats_private_show_as_idle_not_error(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler._active_processes[self.channel.id] = object()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.recorder.should_refresh_stream_source.return_value = False
        scheduler.recorder.platforms.get.return_value.map_recording_failure.return_value = MagicMock(
            message="Streamer unavailable (private show)",
            error_code=MagicMock(value="RECORDER_EXITED"),
            raw_output="private show",
            return_code=1,
        )
        process = MagicMock()
        process.stderr = io.StringIO("private show")
        process.wait.return_value = 1

        with TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "capture.mkv"
            mp4_path = Path(tmpdir) / "capture.mp4"
            scheduler._wait_for_recording(
                self.channel.id,
                process,
                source_path,
                mp4_path,
                ["https://cdn.example/primary.m3u8"],
                0,
                0,
            )

        scheduler.channel_service.update_status.assert_any_call(
            self.channel.id,
            status=Status.IDLE,
            active_pid=None,
            last_error=None,
        )
        scheduler.store.log_info.assert_any_call(
            "stream_unavailable",
            "Streamer unavailable (private show)",
            self.channel.id,
        )

    def test_wait_for_recording_session_salvages_partial_artifact_on_failure(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler._active_processes[self.channel.id] = object()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.recorder.should_refresh_stream_source.return_value = False
        scheduler.recorder.platforms.get.return_value.map_recording_failure.return_value = MagicMock(
            message="Stream source unstable (playlist parse failed)",
            error_code=ErrorCode.PLAYLIST_PARSE_FAILED,
            raw_output="parse failed",
            return_code=1,
        )
        scheduler._transition_session = MagicMock()
        scheduler._fail_session = MagicMock()
        scheduler._convert_recording = MagicMock()

        process = MagicMock()
        process.stderr = io.StringIO("ERROR: #EXTM3U absent")
        process.wait.return_value = 1

        session = MagicMock(id="sess-1", active_pid=1234)
        resolved_source = MagicMock(room_status="public")

        with TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "capture.mkv"
            partial_path = Path(tmpdir) / "capture.mkv.part"
            partial_path.write_bytes(b"partial-media")
            mp4_path = Path(tmpdir) / "capture.mp4"
            scheduler._wait_for_recording_session(
                self.channel.id,
                process,
                source_path,
                mp4_path,
                0,
                session=session,
                resolved_source=resolved_source,
            )

        scheduler._transition_session.assert_called_once_with(
            session,
            RecordingPhase.CONVERTING,
            "Recording failed, salvaging partial file",
            event_type="recording_session_converting",
            source_path=str(partial_path),
            target_path=str(mp4_path),
        )
        scheduler._convert_recording.assert_called_once_with(
            self.channel.id,
            partial_path,
            mp4_path,
        )
        scheduler._fail_session.assert_called_once()
        fail_kwargs = scheduler._fail_session.call_args.kwargs
        self.assertEqual(fail_kwargs["source_path"], str(partial_path))
        self.assertEqual(fail_kwargs["target_path"], str(mp4_path))


if __name__ == "__main__":
    unittest.main()
