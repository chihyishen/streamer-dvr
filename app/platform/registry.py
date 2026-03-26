from __future__ import annotations

from ..domain import Platform
from .base import PlatformAdapter
from .chaturbate import ChaturbatePlatform


class PlatformRegistry:
    def __init__(self) -> None:
        self._platforms: dict[Platform, PlatformAdapter] = {
            Platform.CHATURBATE: ChaturbatePlatform(),
        }

    def get(self, platform: Platform) -> PlatformAdapter:
        return self._platforms[platform]
