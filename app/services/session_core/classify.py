from __future__ import annotations

from ...domain import ErrorCode
from ...platform import RecordingFailure, StreamSourceResult
from .models import FailureCategory


def _normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def classify_resolution_failure(result: StreamSourceResult) -> FailureCategory:
    metadata = result.metadata or {}
    room_status = _normalize_text(str(metadata.get("room_status") or ""))
    lowered = _normalize_text(result.message)
    error_code = result.error_code

    if room_status in {"offline", "not_online", "away", "private", "group_show", "hidden"}:
        return FailureCategory.PLATFORM_UNAVAILABLE
    if error_code == ErrorCode.AUTH_OR_COOKIE_FAILED or "cookie" in lowered or "auth" in lowered:
        return FailureCategory.AUTH_INVALID
    if error_code == ErrorCode.DEPENDENCY_MISSING:
        return FailureCategory.DEPENDENCY_FAILURE
    if error_code == ErrorCode.TIMEOUT or "timed out" in lowered or "deadline exceeded" in lowered:
        return FailureCategory.NETWORK_TRANSIENT
    if error_code in {
        ErrorCode.SOURCE_URL_EXPIRED,
        ErrorCode.SOURCE_RESOLVE_FAILED,
        ErrorCode.PAGE_FETCH_FAILED,
        ErrorCode.PLAYLIST_PARSE_FAILED,
    } and ("403" in lowered or "401" in lowered or "cookie" in lowered or "auth" in lowered or "rejected" in lowered):
        return FailureCategory.AUTH_INVALID
    if room_status == "public" and error_code in {
        ErrorCode.SOURCE_URL_EXPIRED,
        ErrorCode.SOURCE_RESOLVE_FAILED,
        ErrorCode.PAGE_FETCH_FAILED,
        ErrorCode.PLAYLIST_PARSE_FAILED,
    }:
        return FailureCategory.SOURCE_UNSTABLE
    if error_code in {
        ErrorCode.SOURCE_URL_EXPIRED,
        ErrorCode.SOURCE_RESOLVE_FAILED,
        ErrorCode.PAGE_FETCH_FAILED,
        ErrorCode.PLAYLIST_PARSE_FAILED,
    }:
        if "404" in lowered or "m3u8" in lowered or "playlist" in lowered or "parse" in lowered:
            return FailureCategory.SOURCE_UNSTABLE
        return FailureCategory.NETWORK_TRANSIENT
    if "offline" in lowered or "private" in lowered or "hidden" in lowered:
        return FailureCategory.PLATFORM_UNAVAILABLE
    return FailureCategory.UNKNOWN


def classify_recording_failure(failure: RecordingFailure, *, room_status: str | None = None) -> FailureCategory:
    lowered = _normalize_text(failure.message)
    normalized_room_status = _normalize_text(room_status)
    error_code = failure.error_code

    if normalized_room_status in {"offline", "not_online", "away", "private", "group_show", "hidden"}:
        return FailureCategory.PLATFORM_UNAVAILABLE
    if error_code == ErrorCode.DEPENDENCY_MISSING:
        return FailureCategory.DEPENDENCY_FAILURE
    if error_code == ErrorCode.CONVERT_FAILED:
        return FailureCategory.PROCESS_FAILURE
    if error_code == ErrorCode.AUTH_OR_COOKIE_FAILED or "auth" in lowered or "cookie" in lowered:
        return FailureCategory.AUTH_INVALID
    if error_code == ErrorCode.TIMEOUT or "timed out" in lowered or "deadline exceeded" in lowered:
        return FailureCategory.NETWORK_TRANSIENT
    if error_code in {
        ErrorCode.SOURCE_URL_EXPIRED,
        ErrorCode.SOURCE_RESOLVE_FAILED,
        ErrorCode.PLAYLIST_PARSE_FAILED,
    }:
        return FailureCategory.SOURCE_UNSTABLE
    if error_code == ErrorCode.RECORDER_EXITED:
        if "404" in lowered or "playlist" in lowered or "m3u8" in lowered:
            return FailureCategory.SOURCE_UNSTABLE
        if "private" in lowered or "hidden" in lowered or "away" in lowered:
            return FailureCategory.PLATFORM_UNAVAILABLE
        return FailureCategory.PROCESS_FAILURE
    return FailureCategory.UNKNOWN
