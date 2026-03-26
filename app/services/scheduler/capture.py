from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

from ...common import compute_next_check_at, utc_now_iso
from ...domain import ErrorCode, Status


class SchedulerCaptureMixin:
    def _start_recording(self, channel_id: str) -> None:
        with self._record_lock:
            if channel_id in self._active_processes:
                self.channel_service.update_status(channel_id, status=Status.RECORDING, last_error=None)
                return
            try:
                channel = self.channel_service.get_channel(channel_id)
            except KeyError:
                return
            config = self.store.load_config()
            try:
                source_path, mp4_path = self.recorder.compute_paths(channel, config)
                command = self.recorder.build_record_command(channel, config, source_path)
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            except FileNotFoundError as exc:
                self.channel_service.update_status(channel_id, status=Status.ERROR, last_error=f"{exc.args[0]} not found")
                self.store.log_error(ErrorCode.DEPENDENCY_MISSING.value, f"{exc.args[0]} not found", channel_id)
                return

            self._active_processes[channel_id] = process
            self.channel_service.update_status(
                channel_id,
                status=Status.RECORDING,
                active_pid=process.pid,
                last_error=None,
                last_recorded_file=str(source_path),
                last_recorded_at=utc_now_iso(),
            )
            self.store.log_info("recording_started", "Streamer is live, recording started", channel_id, pid=process.pid)
            threading.Thread(
                target=self._wait_for_recording,
                args=(channel_id, process, source_path, mp4_path),
                daemon=True,
            ).start()

    def _wait_for_recording(self, channel_id: str, process: subprocess.Popen[str], source_path: Path, mp4_path: Path) -> None:
        stderr = ""
        if process.stderr:
            stderr = process.stderr.read()
        return_code = process.wait()
        
        with self._record_lock:
            self._active_processes.pop(channel_id, None)

        try:
            channel = self.channel_service.get_channel(channel_id)
        except KeyError:
            return

        # Always restore to IDLE/PAUSED after process exits so next recording can start immediately
        next_status = Status.PAUSED if channel.paused else Status.IDLE
        self.channel_service.update_status(
            channel_id,
            status=next_status,
            active_pid=None,
            next_check_at=compute_next_check_at(channel_id, channel.poll_interval_seconds),
            last_error=None if return_code == 0 else channel.last_error,
        )

        if channel.paused and return_code != 0:
            if source_path.exists() and source_path.stat().st_size > 0:
                self.store.log_info("recording_completed", "Recording stopped, starting conversion", channel_id)
                self._convert_recording(channel_id, source_path, mp4_path)
            else:
                self.store.log_info("recording_stopped", "Recording stopped", channel_id)
            return

        if return_code != 0:
            failure = self.recorder.platforms.get(channel.platform).map_recording_failure(stderr, return_code)
            self.channel_service.update_status(
                channel_id,
                status=Status.ERROR,
                active_pid=None,
                last_error=failure.message,
            )
            self.store.log_error(
                failure.error_code.value,
                failure.message,
                channel_id,
                raw_output=failure.raw_output,
                return_code=failure.return_code,
            )
            return

        self.store.log_info("recording_completed", "Recording finished, starting conversion", channel_id)
        self._convert_recording(channel_id, source_path, mp4_path)

    def _convert_recording(self, channel_id: str, source_path: Path, mp4_path: Path) -> None:
        try:
            channel = self.channel_service.get_channel(channel_id)
        except KeyError:
            return
        config = self.store.load_config()
        try:
            mp4_path.parent.mkdir(parents=True, exist_ok=True)
            command = self.recorder.build_convert_command(source_path, mp4_path)
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
        except FileNotFoundError:
            self.store.log_error(ErrorCode.DEPENDENCY_MISSING.value, "ffmpeg not found", channel_id, raw_output="ffmpeg not found")
            return
        except subprocess.TimeoutExpired:
            self.store.log_error(
                ErrorCode.CONVERT_FAILED.value,
                "Conversion timed out",
                channel_id,
                raw_output="Conversion process timed out after 900s",
            )
            return

        if result.returncode != 0:
            self.store.log_error(
                ErrorCode.CONVERT_FAILED.value,
                result.stderr.strip() or "Conversion failed",
                channel_id,
                raw_output=result.stderr.strip() or None,
                return_code=result.returncode,
            )
            return

        if config.delete_source_after_convert and source_path.exists():
            os.remove(source_path)
        
        # Only update file paths, do NOT touch status as it might be RECORDING again for a new session
        self.channel_service.update_status(
            channel_id,
            last_recorded_file=str(mp4_path),
            last_recorded_at=utc_now_iso(),
        )
        self.store.log_info("convert_completed", "Recording converted to MP4", channel_id, output=str(mp4_path))
