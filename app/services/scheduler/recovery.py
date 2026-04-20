from __future__ import annotations

import os
import signal
import time
from datetime import datetime
from pathlib import Path

from ...common import (
    UnsafePathError,
    compute_next_check_at,
    compute_warmup_check_at,
    safe_join,
    safe_segment,
    utc_now,
    utc_now_iso,
)
from ...domain import ErrorCode, Status
from ..session_core import FailureCategory, RecordingPhase


class SchedulerRecoveryMixin:
    def _pid_exists(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _reconcile_channels(self) -> None:
        for channel in self.channel_service.list_channels():
            if channel.active_pid and self._pid_exists(channel.active_pid):
                if self._is_stalled_recording(channel):
                    self._terminate_stalled_recording(channel)
                else:
                    continue
            if channel.status == Status.RECORDING or channel.active_pid:
                self._recover_stale_recording(channel)

    def _schedule_startup_warmup_checks(self) -> None:
        for channel in self.channel_service.list_channels():
            if not channel.is_active():
                continue
            if channel.status == Status.RECORDING or channel.active_pid:
                continue
            warmup_at = compute_warmup_check_at(channel.id, 30, 120)
            current_next = channel.next_check_at
            if current_next and not self._is_due(current_next):
                try:
                    current_dt = datetime.fromisoformat(current_next)
                    warmup_dt = datetime.fromisoformat(warmup_at)
                except ValueError:
                    current_dt = None
                    warmup_dt = None
                if current_dt and warmup_dt and current_dt <= warmup_dt:
                    continue
            self.channel_service.update_status(channel.id, next_check_at=warmup_at)
        self.store.log_info("startup_warmup_scheduled", "Scheduled warmup checks after worker start")

    def _is_stalled_recording(self, channel) -> bool:
        if not channel.active_pid or channel.status != Status.RECORDING:
            return False
        if not channel.last_recorded_at:
            return False
        try:
            started_at = datetime.fromisoformat(channel.last_recorded_at)
        except ValueError:
            return False
        age_seconds = (utc_now() - started_at).total_seconds()
        if age_seconds < self.STALLED_RECORDING_SECONDS:
            return False
        if not channel.last_recorded_file:
            return True
        source_path = self._resolve_capture_artifact(Path(channel.last_recorded_file))
        if source_path is None:
            return True
        try:
            modified_age = time.time() - source_path.stat().st_mtime
        except FileNotFoundError:
            return True
        return modified_age >= self.STALLED_RECORDING_SECONDS

    def _terminate_stalled_recording(self, channel) -> None:
        pid = channel.active_pid
        if not pid:
            return
        session = self.sessions.get(channel.id)
        if self._pid_exists(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                self.store.log_info("recovery_signal_failed", f"Process with PID {pid} already exited, skipping.", channel.id)
        self.store.log_error(
            ErrorCode.RECORDER_EXITED.value,
            "Recording stalled, recovering state",
            channel.id,
            pid=pid,
            source=channel.last_recorded_file,
        )
        if session is not None:
            self.sessions.fail(
                session,
                phase=RecordingPhase.RECORDING,
                category=FailureCategory.PROCESS_FAILURE,
                message="Recording stalled, recovering state",
                pid=pid,
                source=channel.last_recorded_file,
            )

    def _recover_stale_recording(self, channel) -> None:
        session = self.sessions.get(channel.id) or self.sessions.open(
            channel.id,
            trigger="recovery",
            metadata={"reason": "stale_recording"},
        )
        self.sessions.transition(
            session,
            RecordingPhase.RECOVERING,
            "Recovering stale recording",
            event_type="recording_session_recovering",
        )
        source_path = None
        if channel.last_recorded_file:
            source_path = self._resolve_capture_artifact(Path(channel.last_recorded_file))
        config = self.store.load_config()
        mp4_path = None
        recording_stem = None
        if source_path:
            recording_stem = source_path.name.removesuffix(".part")
            recording_stem = Path(recording_stem).stem
        if source_path and recording_stem:
            try:
                mp4_path = safe_join(
                    Path(config.organized_dir),
                    safe_segment(channel.username, field="channel.username"),
                    f"{Path(recording_stem).name}.mp4",
                )
            except UnsafePathError:
                mp4_path = None
        if mp4_path and mp4_path.exists():
            self.channel_service.update_status(
                channel.id,
                status=Status.PAUSED if channel.paused else Status.IDLE,
                active_pid=None,
                last_recorded_file=str(mp4_path),
                last_recorded_at=utc_now_iso(),
                last_error=None,
                next_check_at=None if channel.paused else compute_next_check_at(channel.id, channel.poll_interval_seconds),
            )
            self.sessions.complete(
                session,
                message="Recovered stale recording state from converted file",
                outcome="completed",
                output=str(mp4_path),
            )
            self.store.log_info(
                "recording_recovered",
                "Recovered stale recording state from converted file",
                channel.id,
                output=str(mp4_path),
            )
            return
        if source_path and mp4_path and source_path.exists() and source_path.stat().st_size > 0:
            self.store.log_info(
                "recording_recovered",
                "Recovered stale recording, starting conversion",
                channel.id,
                source=str(source_path),
                output=str(mp4_path),
            )
            self._convert_recording(channel.id, source_path, mp4_path)
            self.sessions.complete(
                session,
                message="Recovered stale recording by conversion",
                outcome="completed",
                source=str(source_path),
                output=str(mp4_path),
            )
            return
        next_status = Status.PAUSED if channel.paused else Status.IDLE
        self.channel_service.update_status(channel.id, status=next_status, active_pid=None)
        self.sessions.complete(
            session,
            message="Recovered stale recording state",
            outcome="aborted",
            source=str(source_path) if source_path else None,
        )

    def _is_due(self, next_check_at: str | None) -> bool:
        if not next_check_at:
            return True
        try:
            return datetime.fromisoformat(next_check_at) <= utc_now()
        except ValueError:
            return True
