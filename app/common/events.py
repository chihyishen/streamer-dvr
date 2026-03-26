from __future__ import annotations


def summarize_event(event_type: str, message: str) -> str:
    lowered = message.lower()
    if "room is currently offline" in lowered or "performer is currently away" in lowered:
        return "Streamer offline"
    if "private show" in lowered or "private session" in lowered:
        return "Streamer unavailable (private show)"
    if "failed to download m3u8 information" in lowered and "404" in lowered:
        return "Stream source unstable (m3u8 404)"
    if "stream source unstable" in lowered:
        return message
    if event_type == "stream_online":
        return "Streamer online"
    if event_type == "recording_started":
        return "Recording started"
    if event_type == "recording_completed":
        return "Recording finished"
    if event_type == "recording_stop_requested":
        return "Stopping recording"
    if event_type == "recording_stopped":
        return "Recording stopped"
    if event_type == "convert_completed":
        return "Converted to MP4"
    if event_type == "channel_pause_toggled":
        return message
    if "probe timed out" in lowered:
        return "Probe timed out"
    if "cookie" in lowered or "auth" in lowered:
        return "Cookie or auth issue"
    if "hidden session in progress" in lowered:
        return "Cookie or auth issue"
    if "#extm3u absent" in lowered:
        return "Stream source unstable (playlist parse failed)"
    if "interrupted by user" in lowered:
        return "Probe interrupted"
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return "-"
    cleaned = lines[-1]
    cleaned = cleaned.replace("ERROR: [Chaturbate]", "").strip()
    return cleaned


def event_tone(event_type: str, message: str) -> str:
    lowered = message.lower()
    if "room is currently offline" in lowered or "performer is currently away" in lowered:
        return "neutral"
    if "private show" in lowered or "private session" in lowered:
        return "neutral"
    if "stream source unstable" in lowered or ("failed to download m3u8 information" in lowered and "404" in lowered):
        return "neutral"
    if event_type in {"stream_online", "recording_started", "recording_completed", "convert_completed"}:
        return "good"
    if event_type in {"channel_pause_toggled", "config_updated", "recording_stop_requested", "recording_stopped"}:
        return "neutral"
    if "hidden session in progress" in lowered:
        return "neutral"
    return "bad"
