from __future__ import annotations

import subprocess
import threading
import time
import traceback
from pathlib import Path

from ...domain import Status
from ..channel import ChannelService
from ..recorder import RecorderService
from ..session_core import RecordingSessionRegistry
from ...storage import JsonStore
from .handlers.capture import CaptureHandler
from .handlers.commands import CommandHandler
from .handlers.probe import ProbeHandler
from .handlers.recovery import RecoveryHandler


class SchedulerService:
    STALLED_RECORDING_SECONDS = 180
    RETENTION_SWEEP_INTERVAL_SECONDS = 6 * 60 * 60

    def __init__(self, store: JsonStore, channel_service: ChannelService, recorder: RecorderService) -> None:
        self.store = store
        self.channel_service = channel_service
        self.recorder = recorder
        self._running = False
        self._thread: threading.Thread | None = None
        self._probe_slots = threading.Semaphore(1)
        self._record_lock = threading.RLock()
        self._active_processes: dict[str, subprocess.Popen[str]] = {}
        self._last_retention_run_at = 0.0
        self.sessions = RecordingSessionRegistry(store)

        # Instantiate handlers
        self._capture = CaptureHandler(
            store, channel_service, recorder, self.sessions, self._record_lock, self._active_processes, self
        )
        self._probe = ProbeHandler(
            store, channel_service, recorder, self.sessions, self._probe_slots, self._active_processes, self
        )
        self._commands = CommandHandler(
            store, channel_service, self._record_lock, self._active_processes, self._probe
        )
        self._recovery = RecoveryHandler(
            store, channel_service, self.sessions, self.STALLED_RECORDING_SECONDS, self
        )

    def start(self) -> None:
        if self._running:
            return
        config = self.store.load_config()
        self._probe_slots = threading.Semaphore(config.max_concurrent_probes)
        # Update handler's probe_slots as it's a new instance
        self._probe._probe_slots = self._probe_slots
        
        try:
            self._reconcile_channels()
            self._run_retention_if_due(force=True)
            self._schedule_startup_warmup_checks()
            self.store.log_info("scheduler_started", "Scheduler service starting...")
        except Exception as exc:
            self.store.log_error(
                "scheduler_init_failed",
                f"Failed to initialize scheduler: {exc}",
                error_type=type(exc).__name__,
                traceback=traceback.format_exc(),
            )
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self.store.log_info("scheduler_stopped", "Scheduler service stopping...")

    def _run_loop(self) -> None:
        self.store.log_info("scheduler_loop_started", "Scheduler main loop started")
        while self._running:
            try:
                self._run_retention_if_due()
                self._process_commands()
                for channel in self.channel_service.list_channels():
                    try:
                        self._tick_channel(channel)
                    except Exception as exc:
                        self.store.log_error(
                            "scheduler_channel_tick_failed",
                            f"Scheduler tick failed for channel: {exc}",
                            channel.id,
                            error_type=type(exc).__name__,
                            traceback=traceback.format_exc(),
                        )
            except Exception as exc:
                self.store.log_error(
                    "scheduler_loop_error",
                    f"Error in scheduler loop: {exc}",
                    error_type=type(exc).__name__,
                    traceback=traceback.format_exc(),
                )
                time.sleep(5)  # Avoid rapid error cycling
            time.sleep(2)

    def _tick_channel(self, channel) -> None:
        with self._record_lock:
            is_internally_active = channel.id in self._active_processes

        if channel.active_pid and self._pid_exists(channel.active_pid):
            if self._is_stalled_recording(channel):
                self._terminate_stalled_recording(channel)
                self._recover_stale_recording(channel)
            return

        if is_internally_active:
            return

        if channel.active_pid and not self._pid_exists(channel.active_pid):
            self._recover_stale_recording(channel)
            return
        if channel.status == Status.RECORDING and not channel.active_pid:
            self._recover_stale_recording(channel)
            return
        if not channel.is_active() or channel.status == Status.RECORDING:
            return
        if self._is_due(channel.next_check_at):
            self._check_channel(channel.id)

    def _run_retention_if_due(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_retention_run_at) < self.RETENTION_SWEEP_INTERVAL_SECONDS:
            return
        self._last_retention_run_at = now
        try:
            summary = self.store.prune_retained_history()
        except Exception as exc:
            self.store.log_error(
                "log_retention_failed",
                f"Failed to prune retained history: {exc}",
                error_type=type(exc).__name__,
                traceback=traceback.format_exc(),
            )
            return
        if int(summary.get("deleted_total", 0)) <= 0:
            return
        self.store.log_info(
            "log_retention_pruned",
            "Pruned retained logs and finished sessions",
            deleted_total=int(summary.get("deleted_total", 0)),
            deleted_event_logs=int(summary.get("deleted_event_logs", 0)),
            deleted_session_logs=int(summary.get("deleted_session_logs", 0)),
            deleted_sessions=int(summary.get("deleted_sessions", 0)),
            vacuumed=bool(summary.get("vacuumed", False)),
        )

    # Delegated methods (Private/Internal logic used by tests or cross-handlers)
    def _pid_exists(self, pid: int) -> bool:
        return self._recovery.pid_exists(pid)

    def _reconcile_channels(self) -> None:
        self._recovery.reconcile_channels()

    def _schedule_startup_warmup_checks(self) -> None:
        self._recovery.schedule_startup_warmup_checks()

    def _is_stalled_recording(self, channel) -> bool:
        return self._recovery.is_stalled_recording(channel)

    def _terminate_stalled_recording(self, channel) -> None:
        self._recovery.terminate_stalled_recording(channel)

    def _recover_stale_recording(self, channel) -> None:
        self._recovery.recover_stale_recording(channel)

    def _is_due(self, next_check_at: str | None) -> bool:
        return self._recovery.is_due(next_check_at)

    def _process_commands(self) -> None:
        self._commands.process_commands()

    def _check_channel(self, channel_id: str) -> None:
        self._probe.check_channel(channel_id)

    def _check_channel_by_id(self, channel_id: str) -> None:
        self._probe.check_channel_by_id(channel_id)

    def _start_recording(self, *args, **kwargs) -> None:
        self._capture.start_recording(*args, **kwargs)

    def _stop_recording(self, channel_id: str) -> None:
        self._commands.stop_recording(channel_id)

    def _convert_recording(self, *args, **kwargs) -> None:
        self._capture.convert_recording(*args, **kwargs)

    def _resolve_capture_artifact(self, source_path: Path) -> Path | None:
        return self._capture.resolve_capture_artifact(source_path)

    # Public API (Command interface)
    def trigger_check(self, channel_id: str) -> None:
        self._commands.trigger_check(channel_id)

    def pause_channel(self, channel_id: str):
        return self._commands.pause_channel(channel_id)
