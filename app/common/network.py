from __future__ import annotations


def looks_like_stream_edge_5xx(message: str | None) -> bool:
    lowered = (message or "").lower()
    return any(
        phrase in lowered
        for phrase in (
            "http error 500",
            "http error 502",
            "http error 503",
            "server returned 5xx server error reply",
            "server returned 500",
            "server returned 502",
            "server returned 503",
            "bad gateway",
            "service unavailable",
            "internal server error",
        )
    )
