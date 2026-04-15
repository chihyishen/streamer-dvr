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
        self.sessions = MagicMock()


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
        )
        scheduler.sessions.fail.assert_called_once()
        fail_kwargs = scheduler.sessions.fail.call_args.kwargs
        self.assertEqual(fail_kwargs["source_path"], str(partial_path))
        self.assertEqual(fail_kwargs["target_path"], str(mp4_path))


if __name__ == "__main__":
    unittest.main()
