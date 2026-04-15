#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


VIDEOS_DIR = Path("/Volumes/Storage/Camrecs/videos")
ORGANIZED_DIR = Path("/Volumes/Storage/Camrecs/Organized_recs")
FFPROBE_CANDIDATES = ["/opt/homebrew/bin/ffprobe", "ffprobe"]
FFMPEG_CANDIDATES = ["/opt/homebrew/bin/ffmpeg", "ffmpeg"]


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    duration: float | None
    format_name: str | None


@dataclass(frozen=True)
class Candidate:
    stem: str
    ts_path: Path
    mkv_path: Path
    mp4_path: Path
    ts_info: MediaInfo
    mkv_info: MediaInfo
    mp4_info: MediaInfo

    @property
    def ts_vs_mkv_delta(self) -> float | None:
        if self.ts_info.duration is None or self.mkv_info.duration is None:
            return None
        return abs(self.ts_info.duration - self.mkv_info.duration)

    @property
    def ts_vs_mp4_delta(self) -> float | None:
        if self.ts_info.duration is None or self.mp4_info.duration is None:
            return None
        return abs(self.ts_info.duration - self.mp4_info.duration)

    @property
    def relative_delta(self) -> float | None:
        delta = self.ts_vs_mkv_delta
        if delta is None:
            return None
        longest = max(self.ts_info.duration or 0.0, self.mkv_info.duration or 0.0)
        if longest <= 0:
            return None
        return delta / longest


def find_binary(candidates: list[str]) -> str:
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError(f"Missing required binary. Tried: {', '.join(candidates)}")


FFPROBE = find_binary(FFPROBE_CANDIDATES)
FFMPEG = find_binary(FFMPEG_CANDIDATES)


def probe_media(path: Path) -> MediaInfo:
    command = [
        FFPROBE,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return MediaInfo(path=path, duration=None, format_name=None)

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return MediaInfo(path=path, duration=None, format_name=None)

    format_info = payload.get("format") or {}
    raw_duration = format_info.get("duration")
    try:
        duration = float(raw_duration) if raw_duration not in {None, "N/A"} else None
    except (TypeError, ValueError):
        duration = None
    return MediaInfo(path=path, duration=duration, format_name=format_info.get("format_name"))


def iter_candidates(videos_dir: Path, organized_dir: Path) -> list[Candidate]:
    candidates: list[Candidate] = []
    for ts_path in sorted(videos_dir.glob("*.ts")):
        stem = ts_path.stem
        mkv_path = videos_dir / f"{stem}.mkv"
        if not mkv_path.exists():
            continue
        mp4_matches = list(organized_dir.glob(f"*/{stem}.mp4"))
        if len(mp4_matches) != 1:
            continue
        mp4_path = mp4_matches[0]
        candidates.append(
            Candidate(
                stem=stem,
                ts_path=ts_path,
                mkv_path=mkv_path,
                mp4_path=mp4_path,
                ts_info=probe_media(ts_path),
                mkv_info=probe_media(mkv_path),
                mp4_info=probe_media(mp4_path),
            )
        )
    return candidates


def is_safe_match(candidate: Candidate, *, max_delta_seconds: float, max_delta_ratio: float) -> tuple[bool, str]:
    ts_vs_mkv = candidate.ts_vs_mkv_delta
    ts_vs_mp4 = candidate.ts_vs_mp4_delta
    relative = candidate.relative_delta
    if ts_vs_mkv is None or ts_vs_mp4 is None or relative is None:
        return False, "missing ffprobe duration"
    if ts_vs_mkv > max_delta_seconds:
        return False, f"ts/mkv delta {ts_vs_mkv:.2f}s exceeds {max_delta_seconds:.2f}s"
    if relative > max_delta_ratio:
        return False, f"ts/mkv delta {relative * 100:.2f}% exceeds {max_delta_ratio * 100:.2f}%"
    # The current MP4 should also look like the same recording, otherwise replacement is risky.
    if ts_vs_mp4 > (max_delta_seconds * 2):
        return False, f"ts/mp4 delta {ts_vs_mp4:.2f}s exceeds {(max_delta_seconds * 2):.2f}s"
    return True, "durations aligned"


def convert_to_mp4(source_path: Path, target_path: Path) -> None:
    command = [
        FFMPEG,
        "-y",
        "-fflags",
        "+genpts",
        "-i",
        str(source_path),
        "-c:v",
        "copy",
        "-af",
        "aresample=async=1",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        "-movflags",
        "faststart",
        str(target_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"ffmpeg exited with code {result.returncode}")


def replace_mp4_from_ts(candidate: Candidate, *, delete_sources: bool) -> None:
    temp_output = candidate.mp4_path.with_suffix(".ts-replacement.tmp.mp4")
    backup_output = candidate.mp4_path.with_suffix(".mp4.bak")

    if temp_output.exists():
        temp_output.unlink()

    convert_to_mp4(candidate.ts_path, temp_output)

    converted_info = probe_media(temp_output)
    if converted_info.duration is None or candidate.ts_info.duration is None:
        raise RuntimeError("failed to verify converted MP4 duration")

    converted_delta = abs(converted_info.duration - candidate.ts_info.duration)
    if converted_delta > 3.0:
        raise RuntimeError(f"converted MP4 drifted by {converted_delta:.2f}s from TS source")

    if backup_output.exists():
        backup_output.unlink()
    candidate.mp4_path.replace(backup_output)
    temp_output.replace(candidate.mp4_path)

    if delete_sources:
        candidate.ts_path.unlink(missing_ok=True)
        candidate.mkv_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replace organized MP4 files with TS-derived conversions for matched TS/MKV test recordings."
    )
    parser.add_argument("--videos-dir", type=Path, default=VIDEOS_DIR)
    parser.add_argument("--organized-dir", type=Path, default=ORGANIZED_DIR)
    parser.add_argument("--max-delta-seconds", type=float, default=8.0)
    parser.add_argument("--max-delta-ratio", type=float, default=0.02)
    parser.add_argument("--apply", action="store_true", help="Apply changes. Dry-run is the default.")
    parser.add_argument("--delete-sources", action="store_true", help="Delete original .ts and .mkv after successful replacement.")
    args = parser.parse_args()

    candidates = iter_candidates(args.videos_dir, args.organized_dir)
    if not candidates:
        print("No matched TS/MKV pairs with a unique organized MP4 were found.")
        return 0

    safe_candidates: list[Candidate] = []
    skipped = 0
    for candidate in candidates:
        safe, reason = is_safe_match(
            candidate,
            max_delta_seconds=args.max_delta_seconds,
            max_delta_ratio=args.max_delta_ratio,
        )
        status = "SAFE" if safe else "SKIP"
        ts_dur = "-" if candidate.ts_info.duration is None else f"{candidate.ts_info.duration:.2f}"
        mkv_dur = "-" if candidate.mkv_info.duration is None else f"{candidate.mkv_info.duration:.2f}"
        mp4_dur = "-" if candidate.mp4_info.duration is None else f"{candidate.mp4_info.duration:.2f}"
        ts_vs_mkv = "-" if candidate.ts_vs_mkv_delta is None else f"{candidate.ts_vs_mkv_delta:.2f}"
        rel = "-" if candidate.relative_delta is None else f"{candidate.relative_delta * 100:.2f}%"
        print(
            f"[{status}] {candidate.stem} | ts={ts_dur}s | mkv={mkv_dur}s | mp4={mp4_dur}s | "
            f"delta={ts_vs_mkv}s | rel={rel} | {reason}"
        )
        if safe:
            safe_candidates.append(candidate)
        else:
            skipped += 1

    print()
    print(f"Matched pairs: {len(candidates)}")
    print(f"Safe to replace: {len(safe_candidates)}")
    print(f"Skipped: {skipped}")

    if not args.apply:
        print("Dry-run only. Re-run with --apply to replace MP4 files.")
        return 0

    failures = 0
    for candidate in safe_candidates:
        try:
            replace_mp4_from_ts(candidate, delete_sources=args.delete_sources)
            print(f"[DONE] {candidate.stem} -> {candidate.mp4_path}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[ERROR] {candidate.stem}: {exc}", file=sys.stderr)

    print()
    print(f"Applied replacements: {len(safe_candidates) - failures}")
    print(f"Failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
