from __future__ import annotations

from ...platform import PlatformRegistry
from ...storage import JsonStore
from ..channel import ChannelService
from .dependency import RecorderDependencyMixin
from .paths import RecorderPathMixin
from .probe import RecorderProbeMixin


class RecorderService(RecorderDependencyMixin, RecorderProbeMixin, RecorderPathMixin):
    def __init__(self, store: JsonStore, channel_service: ChannelService, platforms: PlatformRegistry) -> None:
        self.store = store
        self.channel_service = channel_service
        self.platforms = platforms
