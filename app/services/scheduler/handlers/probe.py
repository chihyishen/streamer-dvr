from __future__ import annotations

import time

from app.common import compute_next_check_at, failure_backoff_seconds, utc_now_iso
from app.domain import AppConfig, Status
from app.services.session_core import FailureCategory, RecordingPhase


class ProbeHandler:
    def __init__(self, store, channel_service, recorder, sessions, probe_slots, active_processes, service) -> None:
        self.store = store
        self.channel_service = channel_service
        self.recorder = recorder
        self.sessions = sessions
        self._probe_slots = probe_slots
        self._active_processes = active_processes
        self.service = service
        self._last_probe_started_at = 0.0

    def _respect_probe_rate_limit(self, config: AppConfig) -> None:
        wait_for = config.probe_rate_limit_seconds - (time.time() - self._last_probe_started_at)
        if wait_for > 0:
            time.sleep(wait_for)
        self._last_probe_started_at = time.time()

    def check_channel_by_id(self, channel_id: str) -> None:
        self.check_channel(channel_id)

    def check_channel(self, channel_id: str) -> None:
        if not self._probe_slots.acquire(blocking=False):
            return
        try:
            channel = self.channel_service.get_channel(channel_id)
            if channel.id in self._active_processes or channel.active_pid:
                self.channel_service.update_status(channel.id, status=Status.RECORDING, last_error=None)
                return
            config = self.store.load_config()
            self._respect_probe_rate_limit(config)
            self.channel_service.update_status(
                channel.id,
                status=Status.CHECKING,
                last_checked_at=utc_now_iso(),
                next_check_at=compute_next_check_at(channel.id, channel.poll_interval_seconds),
            )
            session = self.sessions.open(channel.id, trigger="probe", metadata={"reason": "scheduled_check"})
            self.sessions.transition(
                session,
                RecordingPhase.PROBING,
                "Starting source resolution",
                event_type="recording_session_probing",
            )
            self.sessions.transition(
                session,
                RecordingPhase.SOURCE_RESOLUTION,
                "Checking stream availability",
                event_type="recording_session_source_resolution",
            )
            resolved_source = self.recorder.acquire_resolved_source(channel, config, session_id=session.id)
            if resolved_source.room_status == "public":
                if resolved_source.stream_url:
                    self.sessions.attach_source(session, resolved_source)
                self.channel_service.update_status(
                    channel.id,
                    status=Status.RECORDING if (channel.id in self._active_processes or channel.active_pid) else Status.CHECKING,
                    last_error=None,
                    last_online_at=utc_now_iso(),
                )
                self.service._start_recording(channel.id, session=session, resolved_source=resolved_source)
                return
            category = resolved_source.failure_category or FailureCategory.UNKNOWN
            next_check = compute_next_check_at(
                channel.id,
                channel.poll_interval_seconds,
                failure_backoff_seconds(category.value),
            )
            updated_status = Status.ERROR if category not in {FailureCategory.PLATFORM_UNAVAILABLE} else Status.IDLE
            self.channel_service.update_status(
                channel.id,
                status=updated_status if not channel.paused else Status.PAUSED,
                last_error=None if category == FailureCategory.PLATFORM_UNAVAILABLE else resolved_source.message,
                next_check_at=next_check,
            )
            if category == FailureCategory.PLATFORM_UNAVAILABLE:
                self.sessions.complete(
                    session,
                    message=resolved_source.message,
                    outcome="aborted",
                    source_fingerprint=resolved_source.source_fingerprint,
                    room_status=resolved_source.room_status,
                )
            else:
                self.sessions.fail(
                    session,
                    phase=RecordingPhase.SOURCE_RESOLUTION,
                    category=category,
                    message=resolved_source.message,
                    raw_output=resolved_source.raw_output,
                    return_code=resolved_source.return_code,
                    source_fingerprint=resolved_source.source_fingerprint,
                    room_status=resolved_source.room_status,
                )
        except KeyError:
            return
        finally:
            self._probe_slots.release()
