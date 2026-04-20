from __future__ import annotations

from pathlib import Path


class UnsafePathError(ValueError):
    """Raised when a user-controlled path segment or resolved path escapes its base."""


def safe_segment(value: str, *, field: str = "segment") -> str:
    """Reject path-separator / traversal tokens in a user-controlled segment."""
    cleaned = (value or "").strip()
    if not cleaned:
        raise UnsafePathError(f"{field} must not be empty")
    if cleaned in {".", ".."}:
        raise UnsafePathError(f"{field} must not be '.' or '..'")
    if "/" in cleaned or "\\" in cleaned or "\x00" in cleaned:
        raise UnsafePathError(f"{field} must not contain path separators or null bytes")
    return cleaned


def safe_join(base: Path, *segments: str) -> Path:
    """Join ``segments`` under ``base`` and verify the result stays inside ``base``.

    ``base`` does not need to exist yet; both paths are resolved with ``strict=False``.
    """
    base_resolved = Path(base).resolve(strict=False)
    cleaned = [safe_segment(seg, field="path segment") for seg in segments]
    candidate = base_resolved.joinpath(*cleaned).resolve(strict=False)
    if not candidate.is_relative_to(base_resolved):
        raise UnsafePathError(f"resolved path {candidate} escapes base {base_resolved}")
    return candidate
