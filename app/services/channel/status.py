from __future__ import annotations

from ...common import compute_next_check_at
from ...domain import AppConfig, Channel, Status


class ChannelStatusMixin:
    def update_status(
        self,
        channel_id: str,
        *,
        status: Status | None = None,
        last_error: str | None | object = ...,
        last_checked_at: str | None | object = ...,
        last_online_at: str | None | object = ...,
        next_check_at: str | None | object = ...,
        active_pid: int | None | object = ...,
        last_recorded_file: str | None | object = ...,
        last_recorded_at: str | None | object = ...,
    ) -> Channel:
        def mutate(channels: list[Channel]) -> Channel:
            for index, channel in enumerate(channels):
                if channel.id != channel_id:
                    continue
                updates: dict[str, object] = {"status": status or channel.status}
                if last_error is not ...:
                    updates["last_error"] = last_error
                if last_checked_at is not ...:
                    updates["last_checked_at"] = last_checked_at
                if last_online_at is not ...:
                    updates["last_online_at"] = last_online_at
                if next_check_at is not ...:
                    updates["next_check_at"] = next_check_at
                if active_pid is not ...:
                    updates["active_pid"] = active_pid
                if last_recorded_file is not ...:
                    updates["last_recorded_file"] = last_recorded_file
                if last_recorded_at is not ...:
                    updates["last_recorded_at"] = last_recorded_at
                updated = channel.model_copy(update=updates)
                channels[index] = updated
                return updated
            raise KeyError(channel_id)

        return self.store.mutate_channels(mutate)

    def set_paused(self, channel_id: str, paused: bool, config: AppConfig, *, log_event: bool = True) -> Channel:
        def mutate(channels: list[Channel]) -> Channel:
            for index, channel in enumerate(channels):
                if channel.id != channel_id:
                    continue
                updated = channel.model_copy(
                    update={
                        "paused": paused,
                        "status": Status.PAUSED if paused else Status.IDLE,
                        "next_check_at": None if paused else compute_next_check_at(channel_id, channel.poll_interval_seconds or config.default_poll_interval_seconds),
                    }
                )
                channels[index] = updated
                return updated
            raise KeyError(channel_id)

        updated = self.store.mutate_channels(mutate)
        if log_event:
            self.store.log_info("channel_pause_toggled", f"Paused={paused}", channel_id)
        return updated

    def clear_error_messages(self, message: str) -> int:
        def mutate(channels: list[Channel]) -> int:
            changed = 0
            for index, channel in enumerate(channels):
                if channel.last_error != message:
                    continue
                next_status = Status.PAUSED if channel.paused else Status.IDLE
                channels[index] = channel.model_copy(update={"last_error": None, "status": next_status})
                changed += 1
            return changed

        changed = self.store.mutate_channels(mutate)
        if changed:
            self.store.log_info("stale_errors_cleared", f"Cleared {changed} stale errors", None, stale_message=message)
        return changed
