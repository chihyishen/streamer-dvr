from __future__ import annotations

from pathlib import Path

from ...common import utc_now
from ...domain import AppConfig, Channel


class RecorderPathMixin:
    def _build_format_selector(self, channel: Channel) -> str:
        filters: list[str] = []
        if channel.max_resolution:
            filters.append(f"height<={channel.max_resolution}")
        if channel.max_framerate:
            filters.append(f"fps<={channel.max_framerate}")
        suffix = f"[{' and '.join(filters)}]" if filters else ""
        return f"bestvideo{suffix}+bestaudio/best{suffix}/best"

    def build_record_command(self, channel: Channel, config: AppConfig, output_path: Path) -> list[str]:
        adapter = self.platforms.get(channel.platform)
        return adapter.build_record_command(
            channel=channel,
            config=config,
            output_path=output_path,
            ensure_dependency=self._ensure_dependency,
            format_selector=self._build_format_selector(channel),
        )

    def build_convert_command(self, source: Path, target: Path) -> list[str]:
        ffmpeg = self._ensure_dependency("ffmpeg", self.store.load_config().ffmpeg_path)
        return [ffmpeg, "-i", str(source), "-c", "copy", "-movflags", "faststart", str(target), "-y"]

    def compute_paths(self, channel: Channel, config: AppConfig) -> tuple[Path, Path]:
        started_at = utc_now().strftime("%Y-%m-%d_%H-%M-%S")
        recordings_dir = Path(config.recordings_dir)
        organized_dir = Path(config.organized_dir) / channel.username
        recordings_dir.mkdir(parents=True, exist_ok=True)
        extension = self.platforms.get(channel.platform).recording_extension()
        base_name = channel.filename_pattern.format(
            streamer=channel.username,
            started_at=started_at,
            ext=extension,
        )
        if "/" in base_name:
            base_name = Path(base_name).name
        source_path = recordings_dir / base_name
        mp4_name = f"{source_path.stem}.mp4" if source_path.suffix else f"{source_path.name}.mp4"
        mp4_path = organized_dir / mp4_name
        return source_path, mp4_path
