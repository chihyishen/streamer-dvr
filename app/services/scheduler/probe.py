from __future__ import annotations

import time

from ...common import compute_next_check_at, failure_backoff_seconds, is_expected_unavailable_message, utc_now_iso
from ...domain import AppConfig, ErrorCode, Status
from ..recorder import RecorderService
from ..session_core import FailureCategory, RecordingPhase


class SchedulerProbeMixin:
    def _is_expected_unavailable(self, message: str | None) -> bool:
        return is_expected_unavailable_message(message)

    def _respect_probe_rate_limit(self, config: AppConfig) -> None:
        wait_for = config.probe_rate_limit_seconds - (time.time() - self._last_probe_started_at)
        if wait_for > 0:
            time.sleep(wait_for)
        self._last_probe_started_at = time.time()

    def _check_channel_by_id(self, channel_id: str) -> None:
        self._check_channel(channel_id)

    def _check_channel(self, channel_id: str) -> None:
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
            if isinstance(self.recorder, RecorderService) and getattr(self, "sessions", None) is not None:
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
                    self._start_recording(channel.id, session=session, resolved_source=resolved_source)
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
                return

            result = self.recorder.probe(channel, config)
            if result.online:
                self.channel_service.update_status(
                    channel.id,
                    status=Status.RECORDING if (channel.id in self._active_processes or channel.active_pid) else Status.CHECKING,
                    last_error=None,
                    last_online_at=utc_now_iso(),
                )
                self._start_recording(channel.id)
                return
            is_expected_unavailable = self._is_expected_unavailable(result.message)
            legacy_failure_category = None
            if result.error_code in {
                ErrorCode.SOURCE_URL_EXPIRED,
                ErrorCode.SOURCE_RESOLVE_FAILED,
                ErrorCode.PAGE_FETCH_FAILED,
                ErrorCode.PLAYLIST_PARSE_FAILED,
            }:
                legacy_failure_category = "source_unstable"
            elif result.error_code == ErrorCode.AUTH_OR_COOKIE_FAILED:
                legacy_failure_category = "auth_invalid"
            elif result.error_code:
                legacy_failure_category = "unknown"
            next_check = compute_next_check_at(
                channel.id,
                channel.poll_interval_seconds,
                failure_backoff_seconds(legacy_failure_category) if result.error_code and not is_expected_unavailable else 0,
            )
            updated_status = Status.ERROR if result.error_code and not is_expected_unavailable else Status.IDLE
            self.channel_service.update_status(
                channel.id,
                status=updated_status if not channel.paused else Status.PAUSED,
                last_error=result.message if result.error_code and not is_expected_unavailable else None,
                next_check_at=next_check,
            )
            if result.error_code and not is_expected_unavailable:
                self.store.log_error(
                    result.error_code.value,
                    result.message,
                    channel.id,
                    raw_output=result.raw_output,
                    return_code=result.return_code,
                )
        except KeyError:
            return
        finally:
            self._probe_slots.release()
