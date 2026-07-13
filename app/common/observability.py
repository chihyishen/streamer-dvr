from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..domain import Event

_REDACTED = "[REDACTED]"
_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")
_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "session",
    "token",
)


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    # Recording session IDs are operational correlation IDs, not credentials.
    if normalized == "session_id" or normalized.endswith("_session_id"):
        return False
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _strip_url_secrets(match: re.Match[str]) -> str:
    value = match.group(0)
    try:
        parts = urlsplit(value)
    except ValueError:
        return _REDACTED
    if not parts.query and not parts.fragment:
        return value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _REDACTED if _is_sensitive_key(key) else _redact(nested)
            for key, nested in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _URL_PATTERN.sub(_strip_url_secrets, value)
    return value


def emit_event_log(event: Event) -> None:
    """Best-effort JSONL emission for the host log collector.

    SQLite remains the source of truth. Any serialization or stdout failure is
    deliberately swallowed so observability cannot affect recording.
    """

    try:
        payload = _redact(event.model_dump(mode="json"))
        payload["service_name"] = "streamer-dvr"
        sys.stdout.write(json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n")
        sys.stdout.flush()
    except Exception:
        return
