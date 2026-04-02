from __future__ import annotations

import argparse
import json
import shlex
import signal
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.domain import Channel, Platform
from app.platform import ChaturbatePlatform


@dataclass
class MethodSpec:
    name: str
    command: list[str]
    output_path: Path


def _channel(username: str) -> Channel:
    return Channel(
        id=username,
        username=username,
        platform=Platform.CHATURBATE,
        url=f"https://chaturbate.com/{username}",
        created_at=1,
    )


def _fetch_chatvideocontext(platform: ChaturbatePlatform, channel: Channel) -> dict[str, Any]:
    request = urllib.request.Request(
        platform.SOURCE_ENDPOINT.format(username=channel.username),
        headers=platform._build_resolve_headers(channel, use_cookies=True),
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        raw_body = response.read().decode("utf-8", errors="replace")
    return json.loads(raw_body)


def _stream_candidates(platform: ChaturbatePlatform, payload: dict[str, Any]) -> list[str]:
    stream_url = str(payload.get("hls_source") or "").strip()
    if not stream_url:
        return []
    return platform._candidate_stream_urls(stream_url)


def _yt_dlp_source_command(platform: ChaturbatePlatform, channel: Channel, url: str, output_path: Path, duration: int) -> list[str]:
    command = [
        ".venv/bin/yt-dlp",
        "--output",
        str(output_path),
        "--format",
        "bestvideo+bestaudio/best",
        "--merge-output-format",
        "mkv",
        "--hls-use-mpegts",
        "--downloader",
        "ffmpeg",
        "--downloader-args",
        f"ffmpeg_i:-t {duration} -hide_banner",
        "--add-header",
        f"Origin: {platform.ORIGIN}",
        "--add-header",
        f"Referer: {channel.url.rstrip('/')}/",
        "--user-agent",
        platform.USER_AGENT,
        url,
    ]
    if platform.COOKIE_PATH.exists():
        command[1:1] = ["--cookies", str(platform.COOKIE_PATH)]
    return command


def _ffmpeg_source_command(platform: ChaturbatePlatform, channel: Channel, url: str, output_path: Path, duration: int, include_cookies: bool) -> list[str]:
    headers = platform._build_record_headers(channel, include_cookies=include_cookies)
    return [
        "/opt/homebrew/bin/ffmpeg",
        "-y",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-user_agent",
        platform.USER_AGENT,
        "-headers",
        headers,
        "-rw_timeout",
        "15000000",
        "-i",
        url,
        "-t",
        str(duration),
        "-c",
        "copy",
        "-f",
        "matroska",
        str(output_path),
    ]


def _channel_yt_dlp_command(platform: ChaturbatePlatform, channel: Channel, output_path: Path, duration: int) -> list[str]:
    return _yt_dlp_source_command(platform, channel, channel.url, output_path, duration)


def _locate_output(output_path: Path) -> Path | None:
    candidates = [
        output_path,
        output_path.with_name(f"{output_path.name}.part"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _probe_media(path: Path) -> dict[str, Any]:
    command = [
        "/opt/homebrew/bin/ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip() or result.stdout.strip() or "ffprobe failed"}
    payload = json.loads(result.stdout or "{}")
    stream_types = [stream.get("codec_type") for stream in payload.get("streams") or []]
    return {
        "ok": bool(stream_types),
        "stream_types": stream_types,
    }


def _run_method(spec: MethodSpec, duration: int) -> dict[str, Any]:
    started_at = time.time()
    result = subprocess.run(spec.command, capture_output=True, text=True, timeout=duration + 30)
    elapsed = round(time.time() - started_at, 3)
    output_file = _locate_output(spec.output_path)
    size_bytes = output_file.stat().st_size if output_file else 0
    media_probe = _probe_media(output_file) if output_file and size_bytes > 0 else {"ok": False, "error": "no output"}
    stderr_excerpt = "\n".join((result.stderr or "").splitlines()[-12:])
    stdout_excerpt = "\n".join((result.stdout or "").splitlines()[-12:])
    return {
        "name": spec.name,
        "return_code": result.returncode,
        "elapsed_seconds": elapsed,
        "size_bytes": size_bytes,
        "output_file": str(output_file) if output_file else None,
        "media_probe": media_probe,
        "stderr_excerpt": stderr_excerpt,
        "stdout_excerpt": stdout_excerpt,
        "command": " ".join(shlex.quote(part) for part in spec.command),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare live recording methods against a Chaturbate channel.")
    parser.add_argument("username", help="Chaturbate username to test")
    parser.add_argument("--duration", type=int, default=15, help="Recording duration per method in seconds")
    parser.add_argument("--output-dir", default="/tmp/chaturbate-method-tests", help="Directory for temporary recordings")
    args = parser.parse_args()

    platform = ChaturbatePlatform()
    channel = _channel(args.username)
    output_dir = Path(args.output_dir) / args.username / str(int(time.time()))
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = _fetch_chatvideocontext(platform, channel)
    room_status = str(payload.get("room_status") or "").lower()
    candidates = _stream_candidates(platform, payload)

    print(json.dumps({
        "username": args.username,
        "room_status": room_status,
        "hls_source": payload.get("hls_source"),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "output_dir": str(output_dir),
    }, ensure_ascii=False, indent=2))

    methods: list[MethodSpec] = [
        MethodSpec(
            name="yt_dlp_channel_url",
            command=_channel_yt_dlp_command(platform, channel, output_dir / "yt_dlp_channel_url.mkv", args.duration),
            output_path=output_dir / "yt_dlp_channel_url.mkv",
        )
    ]
    for index, candidate in enumerate(candidates):
        methods.append(
            MethodSpec(
                name=f"yt_dlp_source_{index}",
                command=_yt_dlp_source_command(platform, channel, candidate, output_dir / f"yt_dlp_source_{index}.mkv", args.duration),
                output_path=output_dir / f"yt_dlp_source_{index}.mkv",
            )
        )
        methods.append(
            MethodSpec(
                name=f"ffmpeg_source_{index}_with_cookies",
                command=_ffmpeg_source_command(
                    platform,
                    channel,
                    candidate,
                    output_dir / f"ffmpeg_source_{index}_with_cookies.mkv",
                    args.duration,
                    include_cookies=True,
                ),
                output_path=output_dir / f"ffmpeg_source_{index}_with_cookies.mkv",
            )
        )
        methods.append(
            MethodSpec(
                name=f"ffmpeg_source_{index}_no_cookies",
                command=_ffmpeg_source_command(
                    platform,
                    channel,
                    candidate,
                    output_dir / f"ffmpeg_source_{index}_no_cookies.mkv",
                    args.duration,
                    include_cookies=False,
                ),
                output_path=output_dir / f"ffmpeg_source_{index}_no_cookies.mkv",
            )
        )

    results = [_run_method(spec, args.duration) for spec in methods]
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
