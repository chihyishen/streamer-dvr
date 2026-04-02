from __future__ import annotations

import os
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from app.domain import Channel, Platform, Status
from app.services.scheduler.recovery import SchedulerRecoveryMixin


class _SchedulerUnderTest(SchedulerRecoveryMixin):
    STALLED_RECORDING_SECONDS = 180

    def __init__(self) -> None:
        self.store = MagicMock()
        self.channel_service = MagicMock()
        self._record_lock = threading.RLock()
        self._convert_recording = MagicMock()


class SchedulerRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.channel = Channel(
            id="chan-1",
            username="alice",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/alice",
            created_at=1,
            status=Status.RECORDING,
            active_pid=4321,
            last_recorded_at="2026-03-28T05:00:00+08:00",
        )

    def test_is_stalled_recording_accepts_active_part_file(self) -> None:
        scheduler = _SchedulerUnderTest()
        with TemporaryDirectory() as tmpdir, patch("app.services.scheduler.recovery.utc_now") as utc_now_mock:
            source_path = Path(tmpdir) / "capture.mkv"
            part_path = Path(f"{source_path}.part")
            part_path.write_bytes(b"data")
            fresh_mtime = time.time() - 30
            os.utime(part_path, (fresh_mtime, fresh_mtime))
            self.channel.last_recorded_file = str(source_path)
            utc_now_mock.return_value = datetime.fromisoformat("2026-03-28T05:04:00+08:00")

            self.assertFalse(scheduler._is_stalled_recording(self.channel))

    def test_recover_stale_recording_converts_part_file(self) -> None:
        scheduler = _SchedulerUnderTest()
        scheduler.store.load_config.return_value.organized_dir = "/organized"
        with TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "capture.mkv"
            part_path = Path(f"{source_path}.part")
            part_path.write_bytes(b"data")
            self.channel.last_recorded_file = str(source_path)
            self.channel.paused = False
            self.channel.status = Status.RECORDING
            self.channel.active_pid = None

            scheduler._recover_stale_recording(self.channel)

        scheduler._convert_recording.assert_called_once_with(
            self.channel.id,
            part_path,
            Path("/organized") / self.channel.username / "capture.mp4",
        )
