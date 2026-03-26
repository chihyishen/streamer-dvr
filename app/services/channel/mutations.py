from __future__ import annotations

import time

from ...common import compute_next_check_at
from ...domain import AppConfig, Channel, ChannelCreate, ChannelUpdate, Platform, Status


class ChannelMutationMixin:
    def list_channels(self) -> list[Channel]:
        return self.store.load_channels()

    def get_channel(self, channel_id: str) -> Channel:
        for channel in self.list_channels():
            if channel.id == channel_id:
                return channel
        raise KeyError(channel_id)

    def upsert(self, channel: Channel) -> None:
        with self._lock:
            def mutate(channels: list[Channel]) -> None:
                for index, existing in enumerate(channels):
                    if existing.id == channel.id:
                        channels[index] = channel
                        return
                channels.append(channel)

            self.store.mutate_channels(mutate)

    def delete(self, channel_id: str) -> None:
        with self._lock:
            def mutate(channels: list[Channel]) -> None:
                channels[:] = [channel for channel in channels if channel.id != channel_id]

            self.store.mutate_channels(mutate)

    def replace(self, current_id: str, channel: Channel) -> None:
        with self._lock:
            def mutate(channels: list[Channel]) -> None:
                for index, existing in enumerate(channels):
                    if existing.id == current_id:
                        channels[index] = channel
                        return
                channels.append(channel)

            self.store.mutate_channels(mutate)

    def create(self, payload: ChannelCreate, config: AppConfig) -> Channel:
        username = payload.username.strip()
        platform = payload.platform or Platform.CHATURBATE
        adapter = self.platforms.get(platform)
        adapter.validate_username(username)
        channel = Channel(
            id=username,
            username=username,
            platform=platform,
            url=adapter.normalize_url(username, payload.url),
            category=payload.category.strip() or "default",
            enabled=payload.enabled,
            paused=payload.paused,
            poll_interval_seconds=payload.poll_interval_seconds or config.default_poll_interval_seconds,
            next_check_at=compute_next_check_at(username, payload.poll_interval_seconds or config.default_poll_interval_seconds),
            max_resolution=payload.max_resolution,
            max_framerate=payload.max_framerate,
            filename_pattern=payload.filename_pattern or "{streamer}_{started_at}.{ext}",
            created_at=int(time.time()),
            status=Status.PAUSED if payload.paused else Status.IDLE,
        )
        self.upsert(channel)
        self.store.log_info("channel_created", "Channel created", channel.id)
        return channel

    def update(self, channel_id: str, payload: ChannelUpdate, config: AppConfig) -> Channel:
        channel = self.get_channel(channel_id)
        next_username = payload.username.strip() if payload.username is not None else channel.username
        if next_username != channel.username and (channel.active_pid or channel.status == Status.RECORDING):
            raise ValueError("Cannot rename a streamer while recording is active")
        if next_username != channel.username:
            duplicate = next((item for item in self.list_channels() if item.id == next_username and item.id != channel_id), None)
            if duplicate:
                raise ValueError(f"Streamer already exists: {next_username}")
        next_platform = payload.platform or channel.platform
        adapter = self.platforms.get(next_platform)
        adapter.validate_username(next_username)
        updates: dict[str, object] = {}
        if next_username != channel.username:
            updates["id"] = next_username
            updates["username"] = next_username
        if payload.platform is not None:
            updates["platform"] = payload.platform
        if payload.url is not None or next_username != channel.username or payload.platform is not None:
            updates["url"] = adapter.normalize_url(next_username, payload.url)
        if payload.category is not None:
            updates["category"] = payload.category.strip() or channel.category
        if payload.enabled is not None:
            updates["enabled"] = payload.enabled
        if payload.paused is not None:
            updates["paused"] = payload.paused
            updates["status"] = Status.PAUSED if payload.paused else Status.IDLE
        if payload.poll_interval_seconds is not None:
            updates["poll_interval_seconds"] = payload.poll_interval_seconds
            if payload.paused is not True:
                updates["next_check_at"] = compute_next_check_at(next_username, payload.poll_interval_seconds)
        updates["max_resolution"] = payload.max_resolution
        updates["max_framerate"] = payload.max_framerate
        if payload.filename_pattern is not None:
            updates["filename_pattern"] = payload.filename_pattern.strip() or channel.filename_pattern
        updated = channel.model_copy(update=updates)
        if not updated.paused and not updated.next_check_at:
            updated = updated.model_copy(
                update={"next_check_at": compute_next_check_at(updated.id, updated.poll_interval_seconds or config.default_poll_interval_seconds)}
            )
        if updated.id != channel_id:
            self.replace(channel_id, updated)
        else:
            self.upsert(updated)
        self.store.log_info("channel_updated", "Channel updated", updated.id)
        return updated
