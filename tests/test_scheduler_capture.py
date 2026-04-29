from __future__ import annotations

import io
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from app.domain import AppConfig, Channel, ErrorCode, Platform, Status
from app.services.session_core import FailureCategory, RecordingPhase
from app.services.scheduler.handlers.capture import CaptureHandler


class _SchedulerUnderTest:
    def __init__(self) -> None:
        self._record_lock = threading.RLock()
        self._active_processes: dict[str, object] = {}
        self.store = MagicMock()
        self.channel_service = MagicMock()
        self.recorder = MagicMock()
        self.sessions = MagicMock()
        self.handler = CaptureHandler(
            self.store,
            self.channel_service,
            self.recorder,
            self.sessions,
            self._record_lock,
            self._active_processes,
            self,
        )

    def _start_recording(self, *args, **kwargs) -> None:
        return self.handler.start_recording(*args, **kwargs)

    def _wait_for_recording(self, *args, **kwargs) -> None:
        return self.handler._wait_for_recording(*args, **kwargs)

    def _convert_recording(self, *args, **kwargs) -> None:
        return self.handler.convert_recording(*args, **kwargs)

    def _resolve_capture_artifact(self, source_path: Path) -> Path | None:
        return self.handler.resolve_capture_artifact(source_path)


class SchedulerCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.channel = Channel(
            id="chan-1",
            username="alice",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/alice",
            created_at=1,
        )

    def test_start_recording_uses_resolved_source_when_platform_prefers_direct_source(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.store.load_config.return_value = AppConfig()
        scheduler.recorder.compute_paths.return_value = (Path("/tmp/capture.mkv"), Path("/tmp/capture.mp4"))
        scheduler.recorder.platforms.get.return_value.record_uses_resolved_source.return_value = True
        scheduler.recorder.build_resolved_record_command.return_value = ["ffmpeg", "https://edge.example/live.m3u8"]

        resolved_source = MagicMock(stream_url="https://edge.example/live.m3u8", room_status="public")
        session = MagicMock(id="sess-1")
        process = MagicMock()
        process.pid = 1234
        thread_mock = MagicMock()

        with patch("subprocess.Popen", return_value=process), patch("threading.Thread", return_value=thread_mock) as thread_ctor:
            scheduler._start_recording(
                self.channel.id,
                session=session,
                resolved_source=resolved_source,
            )

        scheduler.recorder.build_resolved_record_command.assert_called_once_with(
            self.channel,
            scheduler.store.load_config.return_value,
            Path("/tmp/capture.mkv"),
            "https://edge.example/live.m3u8",
        )
        scheduler.recorder.build_record_command.assert_not_called()
        scheduler.sessions.transition.assert_called_once()
        transition_kwargs = scheduler.sessions.transition.call_args.kwargs
        self.assertEqual(transition_kwargs["source_url"], "https://edge.example/live.m3u8")
        self.assertEqual(thread_ctor.call_count, 1)
        thread_mock.start.assert_called_once()

    def test_start_recording_acquires_resolved_source_for_direct_source_platform(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.store.load_config.return_value = AppConfig()
        scheduler.recorder.compute_paths.return_value = (Path("/tmp/capture.mkv"), Path("/tmp/capture.mp4"))
        scheduler.recorder.platforms.get.return_value.record_uses_resolved_source.return_value = True
        scheduler.recorder.build_resolved_record_command.return_value = ["ffmpeg", "https://edge.example/live.m3u8"]
        scheduler.recorder.acquire_resolved_source.return_value = MagicMock(
            stream_url="https://edge.example/live.m3u8",
            room_status="public",
        )

        session = MagicMock(id="sess-1")
        process = MagicMock()
        process.pid = 1234
        thread_mock = MagicMock()

        with patch("subprocess.Popen", return_value=process), patch("threading.Thread", return_value=thread_mock) as thread_ctor:
            scheduler._start_recording(
                self.channel.id,
                session=session,
            )

        scheduler.recorder.acquire_resolved_source.assert_called_once()
        scheduler.recorder.build_resolved_record_command.assert_called_once_with(
            self.channel,
            scheduler.store.load_config.return_value,
            Path("/tmp/capture.mkv"),
            "https://edge.example/live.m3u8",
        )
        scheduler.recorder.build_record_command.assert_not_called()
        self.assertEqual(scheduler.sessions.transition.call_count, 2)
        transition_kwargs = scheduler.sessions.transition.call_args.kwargs
        self.assertEqual(transition_kwargs["source_url"], "https://edge.example/live.m3u8")
        self.assertEqual(thread_ctor.call_count, 1)
        thread_mock.start.assert_called_once()

    def test_wait_for_recording_salvages_partial_artifact_on_failure(self) -> None:
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

        process = MagicMock()
        process.stderr = io.StringIO("ERROR: #EXTM3U absent")
        process.wait.return_value = 1

        scheduler._convert_recording = MagicMock()

        session = MagicMock(id="sess-1", active_pid=1234)
        resolved_source = MagicMock(room_status="public")

        with TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "capture.mkv"
            partial_path = Path(tmpdir) / "capture.mkv.part"
            partial_path.write_bytes(b"partial-media")
            mp4_path = Path(tmpdir) / "capture.mp4"
            scheduler._wait_for_recording(
                self.channel.id,
                process,
                source_path,
                mp4_path,
                0,
                session=session,
                resolved_source=resolved_source,
            )

        scheduler.sessions.transition.assert_called_once_with(
            session,
            RecordingPhase.CONVERTING,
            "Recording failed, salvaging partial file",
            event_type="recording_session_converting",
            level="INFO",
            source_path=str(partial_path),
            target_path=str(mp4_path),
        )
        scheduler._convert_recording.assert_called_once_with(
            self.channel.id,
            partial_path,
            mp4_path,
            failed_recording=True,
        )
        scheduler.sessions.fail.assert_called_once()
        fail_kwargs = scheduler.sessions.fail.call_args.kwargs
        self.assertEqual(fail_kwargs["source_path"], str(partial_path))
        self.assertEqual(fail_kwargs["target_path"], str(mp4_path))

    def test_wait_for_recording_clears_stale_last_recorded_file_when_failure_leaves_no_artifact(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler._active_processes[self.channel.id] = object()
        self.channel.last_recorded_file = "/tmp/capture.mkv"
        self.channel.last_recorded_at = "2026-04-22T21:22:05+08:00"
        self.channel.last_recording_duration_seconds = 12
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.recorder.should_refresh_stream_source.return_value = False
        scheduler.recorder.platforms.get.return_value.map_recording_failure.return_value = MagicMock(
            message="Stream source unavailable (5xx)",
            error_code=ErrorCode.SOURCE_URL_EXPIRED,
            raw_output="HTTP 502",
            return_code=8,
        )

        process = MagicMock()
        process.stderr = io.StringIO("HTTP error 502 Bad Gateway")
        process.wait.return_value = 8

        with TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "capture.mkv"
            mp4_path = Path(tmpdir) / "capture.mp4"
            self.channel.last_recorded_file = str(source_path)
            scheduler._wait_for_recording(
                self.channel.id,
                process,
                source_path,
                mp4_path,
                0,
                session=MagicMock(id="sess-1", active_pid=1234),
                resolved_source=MagicMock(room_status="public", stream_url="https://edge.example/live.m3u8"),
            )

        self.assertIn(
            unittest.mock.call(
                self.channel.id,
                last_recorded_file=None,
                last_recorded_at=None,
                last_recording_duration_seconds=None,
            ),
            scheduler.channel_service.update_status.call_args_list,
        )

    def test_wait_for_recording_converts_existing_artifact_before_source_retry(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler._active_processes[self.channel.id] = object()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.recorder.should_refresh_stream_source.return_value = True
        adapter = scheduler.recorder.platforms.get.return_value
        adapter.record_uses_resolved_source.return_value = True
        adapter.map_recording_failure.return_value = MagicMock(
            message="Stream source unavailable (5xx)",
            error_code=ErrorCode.SOURCE_URL_EXPIRED,
            raw_output="HTTP 502",
            return_code=8,
        )
        scheduler.store.load_config.return_value = AppConfig(keep_failed_source=True)
        scheduler.recorder.compute_source_retry_delay.return_value = 1.0
        refreshed_source = MagicMock(stream_url="https://edge.example/next.m3u8", room_status="public")
        scheduler.recorder.acquire_resolved_source.return_value = refreshed_source
        scheduler._start_recording = MagicMock()
        scheduler._convert_recording = MagicMock()

        process = MagicMock()
        process.stderr = io.StringIO("HTTP error 502 Bad Gateway")
        process.wait.return_value = 8
        session = MagicMock(id="sess-1", active_pid=1234)
        resolved_source = MagicMock(room_status="public", stream_url="https://edge.example/current.m3u8")

        with TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "capture.mkv"
            source_path.write_bytes(b"partial-media")
            mp4_path = Path(tmpdir) / "capture.mp4"
            scheduler._wait_for_recording(
                self.channel.id,
                process,
                source_path,
                mp4_path,
                0,
                session=session,
                resolved_source=resolved_source,
            )

            retry_source_path = Path(tmpdir) / "capture__retry1.mkv"
            retry_mp4_path = Path(tmpdir) / "capture__retry1.mp4"

        scheduler._convert_recording.assert_called_once_with(
            self.channel.id,
            source_path,
            mp4_path,
            failed_recording=True,
        )
        scheduler._start_recording.assert_called_once_with(
            self.channel.id,
            prepared_paths=(retry_source_path, retry_mp4_path),
            retry_attempt=1,
            session=session,
            resolved_source=refreshed_source,
        )
        scheduler.store.log_info.assert_any_call(
            "recording_retry_segmented",
            "Continuing recording in a new segment after source refresh",
            self.channel.id,
            source=str(source_path),
            output=str(mp4_path),
            next_source=str(retry_source_path),
            next_output=str(retry_mp4_path),
            retry_attempt=1,
        )

    def test_wait_for_recording_uses_retry_segment_paths_after_partial_salvage(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler._active_processes[self.channel.id] = object()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.recorder.should_refresh_stream_source.return_value = True
        adapter = scheduler.recorder.platforms.get.return_value
        adapter.record_uses_resolved_source.return_value = True
        adapter.map_recording_failure.return_value = MagicMock(
            message="Stream source unavailable (5xx)",
            error_code=ErrorCode.SOURCE_URL_EXPIRED,
            raw_output="HTTP 502",
            return_code=8,
        )
        scheduler.store.load_config.return_value = AppConfig(keep_failed_source=False)
        scheduler.recorder.compute_source_retry_delay.return_value = 1.0
        scheduler.recorder.acquire_resolved_source.return_value = MagicMock(
            stream_url="https://edge.example/next.m3u8",
            room_status="public",
        )
        scheduler._start_recording = MagicMock()
        scheduler._convert_recording = MagicMock()

        process = MagicMock()
        process.stderr = io.StringIO("HTTP error 502 Bad Gateway")
        process.wait.return_value = 8

        with TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "capture.mkv"
            source_path.write_bytes(b"partial-media")
            mp4_path = Path(tmpdir) / "capture.mp4"
            scheduler._wait_for_recording(
                self.channel.id,
                process,
                source_path,
                mp4_path,
                0,
                session=MagicMock(id="sess-1", active_pid=1234),
                resolved_source=MagicMock(room_status="public", stream_url="https://edge.example/current.m3u8"),
            )

            retry_source_path = Path(tmpdir) / "capture__retry1.mkv"
            retry_mp4_path = Path(tmpdir) / "capture__retry1.mp4"

        scheduler._convert_recording.assert_called_once_with(
            self.channel.id,
            source_path,
            mp4_path,
            failed_recording=True,
        )
        scheduler._start_recording.assert_called_once()
        self.assertEqual(
            scheduler._start_recording.call_args.kwargs["prepared_paths"],
            (retry_source_path, retry_mp4_path),
        )

    def test_convert_recording_keeps_failed_source_when_enabled(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.store.load_config.return_value = AppConfig(
            delete_source_after_convert=True,
            keep_failed_source=True,
        )
        scheduler.recorder.build_convert_command.return_value = ["ffmpeg", "-i", "in", "out"]

        with TemporaryDirectory() as tmpdir, patch("subprocess.run") as run_mock:
            source_path = Path(tmpdir) / "capture.mkv"
            source_path.write_bytes(b"media")
            mp4_path = Path(tmpdir) / "capture.mp4"
            run_mock.return_value = MagicMock(returncode=0, stderr="")

            scheduler._convert_recording(
                self.channel.id,
                source_path,
                mp4_path,
                failed_recording=True,
            )

            self.assertTrue(source_path.exists())

    def test_convert_recording_deletes_failed_source_when_disabled(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.store.load_config.return_value = AppConfig(
            delete_source_after_convert=True,
            keep_failed_source=False,
        )
        scheduler.recorder.build_convert_command.return_value = ["ffmpeg", "-i", "in", "out"]

        with TemporaryDirectory() as tmpdir, patch("subprocess.run") as run_mock:
            source_path = Path(tmpdir) / "capture.mkv"
            source_path.write_bytes(b"media")
            mp4_path = Path(tmpdir) / "capture.mp4"
            run_mock.return_value = MagicMock(returncode=0, stderr="")

            scheduler._convert_recording(
                self.channel.id,
                source_path,
                mp4_path,
                failed_recording=True,
            )

            self.assertFalse(source_path.exists())

    def test_convert_recording_skips_status_update_when_channel_was_deleted(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler.channel_service.get_channel.return_value = self.channel
        scheduler.channel_service.update_status.side_effect = KeyError(self.channel.id)
        scheduler.store.load_config.return_value = AppConfig(delete_source_after_convert=False)
        scheduler.recorder.build_convert_command.return_value = ["ffmpeg", "-i", "in", "out"]

        with TemporaryDirectory() as tmpdir, patch("subprocess.run") as run_mock:
            source_path = Path(tmpdir) / "capture.mkv"
            source_path.write_bytes(b"media")
            mp4_path = Path(tmpdir) / "capture.mp4"
            run_mock.return_value = MagicMock(returncode=0, stderr="")

            scheduler._convert_recording(
                self.channel.id,
                source_path,
                mp4_path,
            )

        scheduler.store.log_info.assert_any_call(
            "channel_update_skipped",
            "Channel status update skipped because channel no longer exists",
            self.channel.id,
        )


if __name__ == "__main__":
    unittest.main()
