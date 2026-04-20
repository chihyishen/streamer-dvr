from __future__ import annotations

import math
import time
from datetime import datetime
from pathlib import Path

from ...common import looks_like_stream_edge_5xx, utc_now_iso
from ...domain import Channel
from ...platform import PlatformRegistry
from ...storage import JsonStore
from ..channel import ChannelService
from ..session_core import (
    FailureCategory,
    ResolvedSource,
    classify_recording_failure,
    classify_resolution_failure,
)
from .dependency import RecorderDependencyMixin
from .paths import RecorderPathMixin
from .probe import RecorderProbeMixin


class RecorderService(RecorderDependencyMixin, RecorderProbeMixin, RecorderPathMixin):
    def __init__(self, store: JsonStore, channel_service: ChannelService, platforms: PlatformRegistry) -> None:
        self.store = store
        self.channel_service = channel_service
        self.platforms = platforms

    def _source_fingerprint(self, stream_url: str | None, metadata: dict | None = None) -> str | None:
        if not stream_url:
            return None
        metadata = metadata or {}
        parts = [
            str(metadata.get("room_status") or "").lower() or None,
            stream_url,
            str(metadata.get("source_expire") or "").strip() or None,
            str(metadata.get("source_variant") or "").strip() or None,
        ]
        return "|".join(part for part in parts if part)

    def _coerce_resolved_source(
        self,
        result,
        *,
        session_id: str,
        validated_at: str | None = None,
    ) -> ResolvedSource:
        metadata = result.metadata or {}
        room_status = str(metadata.get("room_status") or "").lower() or None
        source_candidates = list(metadata.get("source_candidates") or [])
        if not source_candidates and result.stream_url:
            source_candidates = [result.stream_url]
        source_index = source_candidates.index(result.stream_url) if result.stream_url in source_candidates else 0
        failure_category = classify_resolution_failure(result)
        retryable = failure_category in {
            FailureCategory.SOURCE_UNSTABLE,
            FailureCategory.NETWORK_TRANSIENT,
        }
        return ResolvedSource(
            session_id=session_id,
            stream_url=result.stream_url,
            message=result.message,
            room_status=room_status,
            source_candidates=source_candidates,
            source_index=source_index,
            source_fingerprint=self._source_fingerprint(result.stream_url, metadata),
            validated_at=validated_at,
            resolver_tool="platform-api",
            expires_at=self._source_expiry_iso(metadata),
            source_variant=str(metadata.get("source_variant") or "").strip() or None,
            error_code=result.error_code.value if result.error_code else None,
            failure_category=failure_category,
            raw_output=result.raw_output,
            return_code=result.return_code,
            metadata=dict(metadata),
            retryable=retryable,
        )

    def _source_expiry_iso(self, metadata: dict | None) -> str | None:
        metadata = metadata or {}
        raw_value = metadata.get("source_expire")
        if raw_value in {None, ""}:
            return None
        try:
            return datetime.fromtimestamp(int(raw_value)).astimezone().isoformat()
        except (TypeError, ValueError, OSError):
            return None

    def acquire_resolved_source(
        self,
        channel: Channel,
        config,
        *,
        session_id: str,
        retry_attempt: int = 0,
    ) -> ResolvedSource:
        adapter = self.platforms.get(channel.platform)
        if not adapter.record_uses_resolved_source():
            return self._coerce_resolved_source(
                self.resolve_stream_source(channel, config),
                session_id=session_id,
            )
        max_attempts = max(config.source_retry_max_attempts, 0)
        attempt = retry_attempt
        last_resolved = None
        while attempt <= max_attempts:
            if attempt > 0:
                delay = self.compute_source_retry_delay(attempt)
                if delay > 0:
                    time.sleep(delay)
            result = self.resolve_stream_source(channel, config)
            resolved = self._coerce_resolved_source(
                result,
                session_id=session_id,
                validated_at=utc_now_iso() if result.stream_url else None,
            )
            last_resolved = resolved
            if resolved.stream_url:
                return resolved
            if not resolved.retryable or attempt >= max_attempts:
                return resolved
            attempt += 1
        return last_resolved or ResolvedSource(
            session_id=session_id,
            stream_url=None,
            message="Source resolution failed",
            failure_category=FailureCategory.UNKNOWN,
        )

    def build_resolved_record_command(
        self,
        channel: Channel,
        config,
        output_path: Path,
        source_url: str,
    ) -> list[str]:
        return RecorderPathMixin.build_resolved_record_command(self, channel, config, output_path, source_url)

    def classify_recording_failure(self, failure, *, room_status: str | None = None) -> FailureCategory:
        return classify_recording_failure(failure, room_status=room_status)

    def should_refresh_stream_source(self, stderr: str, source_path) -> bool:
        lowered = stderr.lower()
        source_candidates = [source_path, source_path.with_name(f"{source_path.name}.part")]
        source_ready = any(candidate.exists() and candidate.stat().st_size > 0 for candidate in source_candidates)
        if source_ready:
            return False
        return (
            "#extm3u absent" in lowered
            or "failed to download m3u8 information" in lowered and "404" in lowered
            or "http error 404" in lowered
            or "server returned 404 not found" in lowered
            or "http error 403" in lowered
            or "server returned 403 forbidden" in lowered
            or "403 forbidden" in lowered
            or looks_like_stream_edge_5xx(stderr)
            or "manifestloaderror" in lowered
            or "invalid data found when processing input" in lowered
        )

    def compute_source_retry_delay(self, attempt: int) -> float:
        config = self.store.load_config()
        exponent = max(attempt - 1, 0)
        delay = config.source_retry_initial_delay_seconds * math.pow(config.source_retry_backoff_multiplier, exponent)
        return min(delay, config.source_retry_max_delay_seconds)
