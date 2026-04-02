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
    SOURCE_RESOLVE_FAILED = "SOURCE_RESOLVE_FAILED"
    SOURCE_URL_EXPIRED = "SOURCE_URL_EXPIRED"
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


class RecordingSessionStatus(str, Enum):
    QUEUED = "queued"
    PROBING = "probing"
    RESOLVING_SOURCE = "resolving_source"
    RECORDING = "recording"
    CONVERTING = "converting"
    RECOVERING = "recovering"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"
    STALLED = "stalled"

    @classmethod
    def active_values(cls) -> set[str]:
        return {
            cls.QUEUED.value,
            cls.PROBING.value,
            cls.RESOLVING_SOURCE.value,
            cls.RECORDING.value,
            cls.CONVERTING.value,
            cls.RECOVERING.value,
            cls.STALLED.value,
        }


class RecordingSessionPhase(str, Enum):
    QUEUED = "queued"
    PROBING = "probing"
    RESOLVING_SOURCE = "resolving_source"
    RECORDING = "recording"
    CONVERTING = "converting"
    RECOVERING = "recovering"
    FINALIZING = "finalizing"
    ABORTED = "aborted"


class FailureCategory(str, Enum):
    SOURCE_UNSTABLE = "source_unstable"
    AUTH_INVALID = "auth_invalid"
    PLATFORM_UNAVAILABLE = "platform_unavailable"
    NETWORK_TRANSIENT = "network_transient"
    PROCESS_FAILURE = "process_failure"
    STATE_MACHINE_BUG = "state_machine_bug"
    FILESYSTEM_FAILURE = "filesystem_failure"
    DEPENDENCY_FAILURE = "dependency_failure"
    UNKNOWN = "unknown"


class SourceAuthMode(str, Enum):
    COOKIES = "cookies"
    NO_COOKIES = "no_cookies"
    BROWSER = "browser"
    UNKNOWN = "unknown"
