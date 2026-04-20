from __future__ import annotations

from pathlib import Path

from app.common import safe_join, safe_segment, utc_now
from app.domain import AppConfig, Channel


class PathHandler:
    def __init__(self, store, platforms, service) -> None:
        self.store = store
        self.platforms = platforms
        self.service = service

    def _build_format_selector(self, channel: Channel) -> str:
        filters: list[str] = []
        if channel.max_resolution:
            filters.append(f"height<={channel.max_resolution}")
        if channel.max_framerate:
            filters.append(f"fps<={channel.max_framerate}")
        suffix = f"[{' and '.join(filters)}]" if filters else ""
        return f"best{suffix}/bestvideo{suffix}+bestaudio/best"

    def build_record_command(self, channel: Channel, config: AppConfig, output_path: Path, source_url: str) -> list[str]:
        adapter = self.platforms.get(channel.platform)
        return adapter.build_record_command(
            channel=channel,
            config=config,
            output_path=output_path,
            source_url=source_url,
            ensure_dependency=self.service._ensure_dependency,
            format_selector=self._build_format_selector(channel),
        )

    def build_resolved_record_command(self, channel: Channel, config: AppConfig, output_path: Path, source_url: str) -> list[str]:
        adapter = self.platforms.get(channel.platform)
        return adapter.build_record_command_for_source(
            channel=channel,
            config=config,
            output_path=output_path,
            source_url=source_url,
            ensure_dependency=self.service._ensure_dependency,
            format_selector=self._build_format_selector(channel),
        )

    def build_convert_command(self, source: Path, target: Path) -> list[str]:
        config = self.store.load_config()
        ffmpeg = self.service._ensure_dependency("ffmpeg", config.ffmpeg_path)
        command = [
            ffmpeg, "-fflags", "+genpts",
            "-i", str(source),
            "-c:v", "copy",
        ]
        if config.force_audio_reencode:
            command += ["-af", "aresample=async=1", "-c:a", "aac", "-b:a", "128k"]
        else:
            command += ["-c:a", "copy"]
        command += [
            "-shortest",
            "-movflags", "faststart",
            str(target), "-y",
        ]
        return command

    def compute_paths(self, channel: Channel, config: AppConfig) -> tuple[Path, Path]:
        started_at = utc_now().strftime("%Y-%m-%d_%H-%M-%S")
        recordings_base = Path(config.recordings_dir).resolve(strict=False)
        organized_base = Path(config.organized_dir).resolve(strict=False)
        recordings_base.mkdir(parents=True, exist_ok=True)
        username_segment = safe_segment(channel.username, field="channel.username")
        extension = self.platforms.get(channel.platform).recording_extension()
        base_name = channel.filename_pattern.format(
            streamer=username_segment,
            started_at=started_at,
            ext=extension,
        )
        # Strip any traversal a pattern may have injected — collapse to final name.
        base_name = Path(base_name).name
        source_path = safe_join(recordings_base, base_name)
        mp4_stem = source_path.stem if source_path.suffix else source_path.name
        mp4_path = safe_join(organized_base, username_segment, f"{mp4_stem}.mp4")
        return source_path, mp4_path
