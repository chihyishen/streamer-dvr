from __future__ import annotations

import os
import signal
import subprocess
import threading

from ...domain import CommandType, Status


class SchedulerCommandMixin:
    def trigger_check(self, channel_id: str) -> None:
        try:
            channel = self.channel_service.get_channel(channel_id)
        except KeyError:
            return
        if channel.status in {Status.CHECKING, Status.RECORDING}:
            return
        threading.Thread(target=self._check_channel_by_id, args=(channel_id,), daemon=True).start()

    def pause_channel(self, channel_id: str):
        config = self.store.load_config()
        updated = self.channel_service.set_paused(channel_id, True, config)
        self._stop_recording(channel_id)
        return updated

    def _stop_recording(self, channel_id: str) -> None:
        process: subprocess.Popen[str] | None = None
        pid: int | None = None
        with self._record_lock:
            process = self._active_processes.get(channel_id)
            if process:
                pid = process.pid
            else:
                try:
                    pid = self.channel_service.get_channel(channel_id).active_pid
                except KeyError:
                    return
        if process and process.poll() is None:
            process.terminate()
            self.store.log_info("recording_stop_requested", "Recording stop requested", channel_id, pid=process.pid)
            return
        if pid and self._pid_exists(pid):
            os.kill(pid, signal.SIGTERM)
            self.store.log_info("recording_stop_requested", "Recording stop requested", channel_id, pid=pid)

    def _process_commands(self) -> None:
        commands = self.store.claim_pending_commands()
        for command in commands:
            try:
                if command.type == CommandType.CHECK:
                    self.trigger_check(command.channel_id)
                elif command.type == CommandType.PAUSE:
                    self.pause_channel(command.channel_id)
                elif command.type == CommandType.RESUME:
                    config = self.store.load_config()
                    self.channel_service.set_paused(command.channel_id, False, config)
                    self.trigger_check(command.channel_id)
                elif command.type == CommandType.DELETE:
                    self.pause_channel(command.channel_id)
                    self.channel_service.delete(command.channel_id)
            except KeyError:
                self.store.log_info(
                    "worker_command_skipped",
                    "Worker command skipped because channel no longer exists",
                    command.channel_id,
                    command_type=command.type.value,
                )
            finally:
                if command.id is not None:
                    self.store.complete_command(command.id)
