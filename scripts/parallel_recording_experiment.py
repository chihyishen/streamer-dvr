from __future__ import annotations

import argparse
import json
import shlex
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


def _fresh_source_url(platform: ChaturbatePlatform, channel: Channel) -> str:
    payload = _fetch_chatvideocontext(platform, channel)
    return str(payload.get("hls_source") or "").strip()


def _ffmpeg_source_command(
    platform: ChaturbatePlatform,
    channel: Channel,
    url: str,
    output_path: Path,
    duration: int,
    *,
    output_format: str,
) -> list[str]:
    headers = platform._build_record_headers(channel, include_cookies=True)
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
        output_format,
        str(output_path),
    ]


def _yt_dlp_room_page_command(
    platform: ChaturbatePlatform,
    channel: Channel,
    output_path: Path,
    duration: int,
) -> list[str]:
    command = [
        ".venv/bin/yt-dlp",
        "--output",
        str(output_path),
        "--format",
        "bestvideo+bestaudio/best",
        "--merge-output-format",
        "mkv",
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
        channel.url,
    ]
    if platform.COOKIE_PATH.exists():
        command[1:1] = ["--cookies", str(platform.COOKIE_PATH)]
    return command


def build_method_specs(
    *,
    platform: ChaturbatePlatform,
    channel: Channel,
    source_url: str | dict[str, str],
    output_dir: Path,
    duration: int,
) -> list[MethodSpec]:
    def source_for(name: str) -> str:
        if isinstance(source_url, dict):
            return source_url[name]
        return source_url

    return [
        MethodSpec(
            name="yt_dlp_room_page",
            command=_yt_dlp_room_page_command(platform, channel, output_dir / "yt_dlp_room_page.mkv", duration),
            output_path=output_dir / "yt_dlp_room_page.mkv",
        ),
        MethodSpec(
            name="ffmpeg_source_matroska",
            command=_ffmpeg_source_command(
                platform,
                channel,
                source_for("ffmpeg_source_matroska"),
                output_dir / "ffmpeg_source_matroska.mkv",
                duration,
                output_format="matroska",
            ),
            output_path=output_dir / "ffmpeg_source_matroska.mkv",
        ),
        MethodSpec(
            name="ffmpeg_source_mpegts",
            command=_ffmpeg_source_command(
                platform,
                channel,
                source_for("ffmpeg_source_mpegts"),
                output_dir / "ffmpeg_source_mpegts.ts",
                duration,
                output_format="mpegts",
            ),
            output_path=output_dir / "ffmpeg_source_mpegts.ts",
        ),
    ]


def _locate_output(output_path: Path) -> Path | None:
    candidates = [output_path, output_path.with_name(f"{output_path.name}.part")]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def summarize_packet_gaps(packets: list[dict[str, str]], *, threshold_seconds: float = 0.1) -> dict[str, Any]:
    gaps: list[float] = []
    previous_end: float | None = None
    for packet in packets:
        pts_raw = packet.get("pts_time")
        duration_raw = packet.get("duration_time")
        if pts_raw is None:
            continue
        pts_time = float(pts_raw)
        duration_time = float(duration_raw or 0.0)
        if previous_end is not None:
            gap = round(pts_time - previous_end, 3)
            if gap > threshold_seconds:
                gaps.append(gap)
        previous_end = pts_time + duration_time
    return {
        "gap_count": len(gaps),
        "max_gap_seconds": max(gaps) if gaps else 0.0,
        "gaps_seconds": gaps,
    }


def _probe_packets(path: Path, *, codec_type: str) -> dict[str, Any]:
    command = [
        "/opt/homebrew/bin/ffprobe",
        "-v",
        "error",
        "-select_streams",
        codec_type[0],
        "-show_packets",
        "-show_entries",
        "packet=pts_time,duration_time",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip() or result.stdout.strip() or "ffprobe failed"}
    payload = json.loads(result.stdout or "{}")
    packets = payload.get("packets") or []
    return {"ok": True, "packet_count": len(packets), "gap_summary": summarize_packet_gaps(packets)}


def _probe_media(path: Path) -> dict[str, Any]:
    command = [
        "/opt/homebrew/bin/ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=format_name,duration",
        "-show_entries",
        "stream=index,codec_type,codec_name,start_time,duration",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip() or result.stdout.strip() or "ffprobe failed"}
    payload = json.loads(result.stdout or "{}")
    return {
        "ok": True,
        "format": payload.get("format") or {},
        "streams": payload.get("streams") or [],
        "audio_packets": _probe_packets(path, codec_type="audio"),
    }


def _run_methods(methods: list[MethodSpec]) -> list[dict[str, Any]]:
    started_at = time.time()
    running: list[tuple[MethodSpec, subprocess.Popen[str]]] = []
    for spec in methods:
        process = subprocess.Popen(spec.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        running.append((spec, process))

    results: list[dict[str, Any]] = []
    for spec, process in running:
        stdout, stderr = process.communicate()
        output_file = _locate_output(spec.output_path)
        size_bytes = output_file.stat().st_size if output_file else 0
        media_probe = _probe_media(output_file) if output_file and size_bytes > 0 else {"ok": False, "error": "no output"}
        results.append(
            {
                "name": spec.name,
                "return_code": process.returncode,
                "elapsed_seconds": round(time.time() - started_at, 3),
                "size_bytes": size_bytes,
                "output_file": str(output_file) if output_file else None,
                "media_probe": media_probe,
                "stderr_excerpt": "\n".join((stderr or "").splitlines()[-12:]),
                "stdout_excerpt": "\n".join((stdout or "").splitlines()[-12:]),
                "command": " ".join(shlex.quote(part) for part in spec.command),
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Record the same Chaturbate live window via multiple methods in parallel.")
    parser.add_argument("username", help="Chaturbate username to test")
    parser.add_argument("--duration", type=int, default=600, help="Recording duration in seconds")
    parser.add_argument("--output-dir", default="/tmp/chaturbate-method-tests", help="Directory for test recordings")
    args = parser.parse_args()

    platform = ChaturbatePlatform()
    channel = _channel(args.username)
    payload = _fetch_chatvideocontext(platform, channel)
    source_url = str(payload.get("hls_source") or "").strip()
    if not source_url:
        print(json.dumps({"username": args.username, "error": "No hls_source returned", "payload": payload}, ensure_ascii=False, indent=2))
        return 1

    output_dir = Path(args.output_dir) / args.username / str(int(time.time()))
    output_dir.mkdir(parents=True, exist_ok=True)
    direct_source_urls = {
        "ffmpeg_source_matroska": _fresh_source_url(platform, channel),
        "ffmpeg_source_mpegts": _fresh_source_url(platform, channel),
    }
    methods = build_method_specs(
        platform=platform,
        channel=channel,
        source_url=direct_source_urls,
        output_dir=output_dir,
        duration=args.duration,
    )

    print(
        json.dumps(
            {
                "username": args.username,
                "room_status": payload.get("room_status"),
                "source_url": source_url,
                "direct_source_urls": direct_source_urls,
                "output_dir": str(output_dir),
                "methods": [spec.name for spec in methods],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(json.dumps({"results": _run_methods(methods)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
