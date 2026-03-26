from __future__ import annotations

import time

from ...common import compute_next_check_at, utc_now_iso
from ...domain import AppConfig, Status


class SchedulerProbeMixin:
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
            next_check = compute_next_check_at(channel.id, channel.poll_interval_seconds, 120 if result.error_code else 0)
            updated_status = Status.ERROR if result.error_code else Status.IDLE
            self.channel_service.update_status(
                channel.id,
                status=updated_status if not channel.paused else Status.PAUSED,
                last_error=result.message if result.error_code else None,
                next_check_at=next_check,
            )
            if result.error_code:
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
