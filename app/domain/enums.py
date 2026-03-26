from __future__ import annotations

from enum import Enum


class Status(str, Enum):
    IDLE = "idle"
    CHECKING = "checking"
    RECORDING = "recording"
    PAUSED = "paused"
    ERROR = "error"


class Platform(str, Enum):
    CHATURBATE = "chaturbate"


class ErrorCode(str, Enum):
    PAGE_FETCH_FAILED = "PAGE_FETCH_FAILED"
    PLAYLIST_PARSE_FAILED = "PLAYLIST_PARSE_FAILED"
    AUTH_OR_COOKIE_FAILED = "AUTH_OR_COOKIE_FAILED"
    TIMEOUT = "TIMEOUT"
    RECORDER_EXITED = "RECORDER_EXITED"
    CONVERT_FAILED = "CONVERT_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"


class CommandType(str, Enum):
    CHECK = "check"
    PAUSE = "pause"
    RESUME = "resume"
    DELETE = "delete"
