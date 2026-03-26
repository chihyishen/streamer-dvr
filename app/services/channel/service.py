from __future__ import annotations

import threading

from ...platform import PlatformRegistry
from ...storage import JsonStore
from .mutations import ChannelMutationMixin
from .status import ChannelStatusMixin


class ChannelService(ChannelMutationMixin, ChannelStatusMixin):
    def __init__(self, store: JsonStore, platforms: PlatformRegistry) -> None:
        self.store = store
        self.platforms = platforms
        self._lock = threading.RLock()
