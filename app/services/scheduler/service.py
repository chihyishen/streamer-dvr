from __future__ import annotations

import subprocess
import threading
import time

from ...domain import Status
from ..channel import ChannelService
from ..recorder import RecorderService
from ..session_core import RecordingSessionRegistry
from ...storage import JsonStore
from .capture import SchedulerCaptureMixin
from .commands import SchedulerCommandMixin
from .probe import SchedulerProbeMixin
from .recovery import SchedulerRecoveryMixin


class SchedulerService(SchedulerRecoveryMixin, SchedulerCommandMixin, SchedulerProbeMixin, SchedulerCaptureMixin):
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
        self._last_probe_started_at = 0.0
        self._last_retention_run_at = 0.0
        self.sessions = RecordingSessionRegistry(store)

    def start(self) -> None:
        if self._running:
            return
        config = self.store.load_config()
        self._probe_slots = threading.Semaphore(config.max_concurrent_probes)
        try:
            self._reconcile_channels()
            self._run_retention_if_due(force=True)
            self._schedule_startup_warmup_checks()
            self.store.log_info("scheduler_started", "Scheduler service starting...")
        except Exception as e:
            self.store.log_error("scheduler_init_failed", f"Failed to initialize scheduler: {str(e)}")
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
                    with self._record_lock:
                        is_internally_active = channel.id in self._active_processes

                    if channel.active_pid and self._pid_exists(channel.active_pid):
                        if self._is_stalled_recording(channel):
                            self._terminate_stalled_recording(channel)
                            self._recover_stale_recording(channel)
                        continue
                    
                    if is_internally_active:
                        continue

                    if channel.active_pid and not self._pid_exists(channel.active_pid):
                        self._recover_stale_recording(channel)
                        continue
                    if channel.status == Status.RECORDING and not channel.active_pid:
                        self._recover_stale_recording(channel)
                        continue
                    if not channel.is_active() or channel.status == Status.RECORDING:
                        continue
                    if self._is_due(channel.next_check_at):
                        self._check_channel(channel.id)
            except Exception as e:
                self.store.log_error("scheduler_loop_error", f"Error in scheduler loop: {str(e)}")
                time.sleep(5) # Avoid rapid error cycling
            time.sleep(2)

    def _run_retention_if_due(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_retention_run_at) < self.RETENTION_SWEEP_INTERVAL_SECONDS:
            return
        self._last_retention_run_at = now
        try:
            summary = self.store.prune_retained_history()
        except Exception as e:
            self.store.log_error("log_retention_failed", f"Failed to prune retained history: {str(e)}")
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
