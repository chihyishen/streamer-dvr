from __future__ import annotations

from dataclasses import dataclass

from .platform import PlatformRegistry
from .services import ChannelService, ConfigService, RecorderService, SchedulerService
from .storage import JsonStore


@dataclass
class AppServices:
    store: JsonStore
    platform_registry: PlatformRegistry
    channel_service: ChannelService
    config_service: ConfigService
    recorder_service: RecorderService
    scheduler_service: SchedulerService


def build_services() -> AppServices:
    store = JsonStore()
    store.ensure_files()
    platform_registry = PlatformRegistry()
    channel_service = ChannelService(store, platform_registry)
    config_service = ConfigService(store)
    recorder_service = RecorderService(store, channel_service, platform_registry)
    scheduler_service = SchedulerService(store, channel_service, recorder_service)
    channel_service.clear_error_messages("yt-dlp not found")
    return AppServices(
        store=store,
        platform_registry=platform_registry,
        channel_service=channel_service,
        config_service=config_service,
        recorder_service=recorder_service,
        scheduler_service=scheduler_service,
    )
