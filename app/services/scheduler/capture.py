from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

from ...common import compute_next_check_at, failure_backoff_seconds, is_expected_unavailable_message, utc_now_iso
from ...domain import ErrorCode, Status
from ..recorder import RecorderService
from ..session_core import FailureCategory, RecordingPhase, ResolvedSource, classify_recording_failure


class SchedulerCaptureMixin:
    def _session_registry(self):
        return getattr(self, "sessions", None)

    def _is_session_runtime(self) -> bool:
        return isinstance(self.recorder, RecorderService) and self._session_registry() is not None

    def _active_session(self, channel_id: str):
        registry = self._session_registry()
        if registry is None:
            return None
        return registry.get(channel_id)

    def _open_session(self, channel_id: str, *, trigger: str, metadata: dict[str, object] | None = None):
        registry = self._session_registry()
        if registry is None:
            return None
        return registry.open(channel_id, trigger=trigger, metadata=metadata)

    def _attach_session_source(self, session, source: ResolvedSource) -> None:
        registry = self._session_registry()
        if registry is not None and session is not None:
            registry.attach_source(session, source)

    def _transition_session(self, session, phase: RecordingPhase, message: str, *, event_type: str, level: str = "INFO", **metadata: object) -> None:
        registry = self._session_registry()
        if registry is not None and session is not None:
            registry.transition(session, phase, message, event_type=event_type, level=level, **metadata)

    def _complete_session(self, session, *, message: str, outcome: str = "completed", **metadata: object) -> None:
        registry = self._session_registry()
        if registry is not None and session is not None:
            registry.complete(session, message=message, outcome=outcome, **metadata)

    def _fail_session(
        self,
        session,
        *,
        phase: RecordingPhase,
        category: FailureCategory,
        message: str,
        event_type: str = "recording_session_failed",
        **metadata: object,
    ) -> None:
        registry = self._session_registry()
        if registry is not None and session is not None:
            registry.fail(session, phase=phase, category=category, message=message, event_type=event_type, **metadata)

    def _is_expected_unavailable(self, message: str | None) -> bool:
        return is_expected_unavailable_message(message)

    def _retryable_resolution_error(self, error_code: ErrorCode | None) -> bool:
        return error_code in {
            ErrorCode.SOURCE_URL_EXPIRED,
            ErrorCode.SOURCE_RESOLVE_FAILED,
            ErrorCode.PLAYLIST_PARSE_FAILED,
            ErrorCode.TIMEOUT,
        }

    def _resolve_source_with_backoff(self, channel_id: str, channel, config, initial_attempt: int) -> object:
        max_attempts = max(config.source_retry_max_attempts, 0)
        attempt = initial_attempt
        last_result = None
        while attempt <= max_attempts:
            if attempt > 0:
                delay = self.recorder.compute_source_retry_delay(attempt)
                self.store.log_info(
                    "source_refresh_retry",
                    f"Stream source refresh attempt {attempt}/{max_attempts} after {delay:.1f}s",
                    channel_id,
                    retry_attempt=attempt,
                    retry_delay_seconds=delay,
                )
                time.sleep(delay)
            result = self.recorder.resolve_stream_source(channel, config)
            last_result = result
            if result.stream_url:
                return result
            if not self._retryable_resolution_error(result.error_code) or attempt >= max_attempts:
                break
            metadata = result.metadata or {}
            self.store.log_error(
                result.error_code.value if result.error_code else ErrorCode.SOURCE_RESOLVE_FAILED.value,
                result.message,
                channel_id,
                raw_output=result.raw_output,
                return_code=result.return_code,
                retry_attempt=attempt,
                edge_region=metadata.get("edge_region"),
                source_expire=metadata.get("source_expire"),
                source_path_tail=metadata.get("source_path_tail"),
            )
            attempt += 1
        return last_result

    def _start_recording(
        self,
        channel_id: str,
        *,
        prepared_paths: tuple[Path, Path] | None = None,
        source_url: str | None = None,
        source_candidates: list[str] | None = None,
        source_index: int = 0,
        retry_attempt: int = 0,
        session=None,
        resolved_source: ResolvedSource | None = None,
    ) -> None:
        if self._is_session_runtime():
            return self._start_recording_session(
                channel_id,
                prepared_paths=prepared_paths,
                source_url=source_url,
                retry_attempt=retry_attempt,
                session=session or self._active_session(channel_id),
                resolved_source=resolved_source,
            )
        with self._record_lock:
            if channel_id in self._active_processes:
                self.channel_service.update_status(channel_id, status=Status.RECORDING, last_error=None)
                return
            try:
                channel = self.channel_service.get_channel(channel_id)
            except KeyError:
                return
            config = self.store.load_config()
            try:
                source_path, mp4_path = prepared_paths or self.recorder.compute_paths(channel, config)
                resolution = None
                resolved_source = source_url
                adapter = self.recorder.platforms.get(channel.platform)
                if not adapter.record_uses_resolved_source():
                    resolved_source = channel.url
                    source_candidates = [channel.url]
                    source_index = 0
                elif not resolved_source:
                    resolution = self._resolve_source_with_backoff(channel_id, channel, config, retry_attempt)
                    resolved_source = resolution.stream_url
                    source_candidates = list((resolution.metadata or {}).get("source_candidates") or ([resolved_source] if resolved_source else []))
                    source_index = source_candidates.index(resolved_source) if resolved_source in source_candidates else 0
                elif not source_candidates and resolved_source:
                    source_candidates = [resolved_source]
                if not resolved_source:
                    next_status = Status.PAUSED if channel.paused else (Status.ERROR if resolution.error_code else Status.IDLE)
                    self.channel_service.update_status(
                        channel_id,
                        status=next_status,
                        last_error=resolution.message if resolution.error_code else None,
                    )
                    log_method = self.store.log_error if resolution.error_code else self.store.log_info
                    log_method(
                        resolution.error_code.value if resolution.error_code else "source_resolve_skipped",
                        resolution.message,
                        channel_id,
                        raw_output=resolution.raw_output,
                        return_code=resolution.return_code,
                        edge_region=(resolution.metadata or {}).get("edge_region") if resolution else None,
                        source_expire=(resolution.metadata or {}).get("source_expire") if resolution else None,
                        source_path_tail=(resolution.metadata or {}).get("source_path_tail") if resolution else None,
                    )
                    return
                command = self.recorder.build_record_command(channel, config, source_path, resolved_source)
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            except FileNotFoundError as exc:
                self.channel_service.update_status(channel_id, status=Status.ERROR, last_error=f"{exc.args[0]} not found")
                self.store.log_error(ErrorCode.DEPENDENCY_MISSING.value, f"{exc.args[0]} not found", channel_id)
                return

            self._active_processes[channel_id] = process
            self.channel_service.update_status(
                channel_id,
                status=Status.RECORDING,
                active_pid=process.pid,
                last_error=None,
                last_recorded_file=str(source_path),
                last_recorded_at=utc_now_iso(),
            )
            self.store.log_info("recording_started", "Streamer is live, recording started", channel_id, pid=process.pid)
            threading.Thread(
                target=self._wait_for_recording,
                args=(channel_id, process, source_path, mp4_path, source_candidates or [resolved_source], source_index, retry_attempt),
                daemon=True,
            ).start()

    def _start_recording_session(
        self,
        channel_id: str,
        *,
        prepared_paths: tuple[Path, Path] | None = None,
        source_url: str | None = None,
        retry_attempt: int = 0,
        session=None,
        resolved_source: ResolvedSource | None = None,
    ) -> None:
        with self._record_lock:
            if channel_id in self._active_processes:
                self.channel_service.update_status(channel_id, status=Status.RECORDING, last_error=None)
                return
            try:
                channel = self.channel_service.get_channel(channel_id)
            except KeyError:
                return
            config = self.store.load_config()
            source_path, mp4_path = prepared_paths or self.recorder.compute_paths(channel, config)
            session = session or self._open_session(channel_id, trigger="record", metadata={"reason": "recording_started"})
            adapter = self.recorder.platforms.get(channel.platform)
            if resolved_source is None and adapter.record_uses_resolved_source():
                self._transition_session(
                    session,
                    RecordingPhase.SOURCE_RESOLUTION,
                    "Checking stream availability",
                    event_type="recording_session_source_resolution",
                    retry_attempt=retry_attempt,
                )
                resolved_source = self.recorder.acquire_resolved_source(
                    channel,
                    config,
                    session_id=session.id if session else channel_id,
                    retry_attempt=retry_attempt,
                )
            if adapter.record_uses_resolved_source() and (resolved_source is None or not resolved_source.stream_url):
                category = resolved_source.failure_category or FailureCategory.UNKNOWN
                next_status = Status.PAUSED if channel.paused else (Status.IDLE if category == FailureCategory.PLATFORM_UNAVAILABLE else Status.ERROR)
                self.channel_service.update_status(
                    channel_id,
                    status=next_status,
                    last_error=None if category == FailureCategory.PLATFORM_UNAVAILABLE else resolved_source.message,
                    next_check_at=compute_next_check_at(
                        channel_id,
                        channel.poll_interval_seconds,
                        failure_backoff_seconds(category.value),
                    ),
                )
                if category == FailureCategory.PLATFORM_UNAVAILABLE:
                    self._complete_session(
                        session,
                        message=resolved_source.message,
                        outcome="aborted",
                        source_fingerprint=resolved_source.source_fingerprint,
                        source_url=resolved_source.stream_url,
                        room_status=resolved_source.room_status,
                    )
                else:
                    self._fail_session(
                        session,
                        phase=RecordingPhase.SOURCE_RESOLUTION,
                        category=category,
                        message=resolved_source.message,
                        raw_output=resolved_source.raw_output,
                        return_code=resolved_source.return_code,
                        source_fingerprint=resolved_source.source_fingerprint,
                        source_url=resolved_source.stream_url,
                        room_status=resolved_source.room_status,
                    )
                return
            if resolved_source is not None and resolved_source.stream_url:
                self._attach_session_source(session, resolved_source)
            if adapter.record_uses_resolved_source():
                record_target = resolved_source.stream_url
                command = self.recorder.build_resolved_record_command(channel, config, source_path, record_target)
            else:
                record_target = channel.url
                command = self.recorder.build_record_command(channel, config, source_path, record_target)
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            self._active_processes[channel_id] = process
            self.channel_service.update_status(
                channel_id,
                status=Status.RECORDING,
                active_pid=process.pid,
                last_error=None,
                last_recorded_file=str(source_path),
                last_recorded_at=utc_now_iso(),
            )
            if session is not None:
                session.active_pid = process.pid
            self._transition_session(
                session,
                RecordingPhase.RECORDING,
                "Recording started",
                event_type="recording_session_recording",
                active_pid=process.pid,
                source_path=str(source_path),
                source_url=record_target,
                retry_attempt=retry_attempt,
            )
            threading.Thread(
                target=self._wait_for_recording,
                args=(channel_id, process, source_path, mp4_path, [record_target], 0, retry_attempt, session, resolved_source),
                daemon=True,
            ).start()

    def _wait_for_recording(
        self,
        channel_id: str,
        process: subprocess.Popen[str],
        source_path: Path,
        mp4_path: Path,
        source_candidates: list[str],
        source_index: int,
        retry_attempt: int,
        session=None,
        resolved_source: ResolvedSource | None = None,
    ) -> None:
        if self._is_session_runtime():
            return self._wait_for_recording_session(
                channel_id,
                process,
                source_path,
                mp4_path,
                retry_attempt,
                session=session or self._active_session(channel_id),
                resolved_source=resolved_source,
            )
        stderr = ""
        if process.stderr:
            stderr = process.stderr.read()
        return_code = process.wait()
        
        with self._record_lock:
            self._active_processes.pop(channel_id, None)

        try:
            channel = self.channel_service.get_channel(channel_id)
        except KeyError:
            return

        # Always restore to IDLE/PAUSED after process exits so next recording can start immediately
        next_status = Status.PAUSED if channel.paused else Status.IDLE
        self.channel_service.update_status(
            channel_id,
            status=next_status,
            active_pid=None,
            next_check_at=compute_next_check_at(channel_id, channel.poll_interval_seconds),
            last_error=None if return_code == 0 else channel.last_error,
        )

        if channel.paused and return_code != 0:
            if source_path.exists() and source_path.stat().st_size > 0:
                self.store.log_info("recording_completed", "Recording stopped, starting conversion", channel_id)
                self._convert_recording(channel_id, source_path, mp4_path)
            else:
                self.store.log_info("recording_stopped", "Recording stopped", channel_id)
            return

        if return_code != 0:
            failure = self.recorder.platforms.get(channel.platform).map_recording_failure(stderr, return_code)
            if self.recorder.should_refresh_stream_source(stderr, source_path):
                if source_index + 1 < len(source_candidates):
                    next_source_index = source_index + 1
                    next_source_url = source_candidates[next_source_index]
                    self.store.log_info(
                        "source_candidate_retry",
                        f"Retrying alternate stream source {next_source_index + 1}/{len(source_candidates)}",
                        channel_id,
                        retry_attempt=retry_attempt,
                        source_path_tail=Path(next_source_url).name,
                    )
                    self._start_recording(
                        channel_id,
                        prepared_paths=(source_path, mp4_path),
                        source_url=next_source_url,
                        source_candidates=source_candidates,
                        source_index=next_source_index,
                        retry_attempt=retry_attempt,
                    )
                    return
                config = self.store.load_config()
                max_attempts = max(config.source_retry_max_attempts, 0)
                attempt = retry_attempt
                while attempt < max_attempts:
                    attempt += 1
                    delay = self.recorder.compute_source_retry_delay(attempt)
                    self.store.log_info(
                        "source_refresh_retry",
                        f"Stream source refresh attempt {attempt}/{max_attempts} after {delay:.1f}s",
                        channel_id,
                        retry_attempt=attempt,
                        retry_delay_seconds=delay,
                    )
                    time.sleep(delay)
                    refresh_result = self.recorder.resolve_stream_source(channel, config)
                    if refresh_result.stream_url:
                        refreshed_candidates = list((refresh_result.metadata or {}).get("source_candidates") or [refresh_result.stream_url])
                        refreshed_index = refreshed_candidates.index(refresh_result.stream_url) if refresh_result.stream_url in refreshed_candidates else 0
                        self._start_recording(
                            channel_id,
                            prepared_paths=(source_path, mp4_path),
                            source_url=refresh_result.stream_url,
                            source_candidates=refreshed_candidates,
                            source_index=refreshed_index,
                            retry_attempt=attempt,
                        )
                        return
                    self.store.log_error(
                        refresh_result.error_code.value if refresh_result.error_code else ErrorCode.SOURCE_RESOLVE_FAILED.value,
                        refresh_result.message,
                        channel_id,
                        raw_output=refresh_result.raw_output,
                        return_code=refresh_result.return_code,
                        retry_attempt=attempt,
                        edge_region=(refresh_result.metadata or {}).get("edge_region"),
                        source_expire=(refresh_result.metadata or {}).get("source_expire"),
                        source_path_tail=(refresh_result.metadata or {}).get("source_path_tail"),
                    )
                self.channel_service.update_status(
                    channel_id,
                    status=Status.ERROR,
                    active_pid=None,
                    last_error="Stream source refresh exhausted",
                )
                self.store.log_error(
                    ErrorCode.SOURCE_URL_EXPIRED.value,
                    "Stream source refresh exhausted",
                    channel_id,
                    raw_output=failure.raw_output,
                    return_code=failure.return_code,
                    retry_attempt=max(retry_attempt, max_attempts),
                )
                return
            if self._is_expected_unavailable(failure.message):
                self.channel_service.update_status(
                    channel_id,
                    status=Status.PAUSED if channel.paused else Status.IDLE,
                    active_pid=None,
                    last_error=None,
                )
                self.store.log_info(
                    "stream_unavailable",
                    failure.message,
                    channel_id,
                )
                return
            self.channel_service.update_status(
                channel_id,
                status=Status.ERROR,
                active_pid=None,
                last_error=failure.message,
            )
            self.store.log_error(
                failure.error_code.value,
                failure.message,
                channel_id,
                raw_output=failure.raw_output,
                return_code=failure.return_code,
            )
            return

        self.store.log_info("recording_completed", "Recording finished, starting conversion", channel_id)
        self._convert_recording(channel_id, source_path, mp4_path)

    def _convert_recording(self, channel_id: str, source_path: Path, mp4_path: Path) -> None:
        try:
            channel = self.channel_service.get_channel(channel_id)
        except KeyError:
            return
        config = self.store.load_config()
        try:
            mp4_path.parent.mkdir(parents=True, exist_ok=True)
            command = self.recorder.build_convert_command(source_path, mp4_path)
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
        except FileNotFoundError:
            self.store.log_error(ErrorCode.DEPENDENCY_MISSING.value, "ffmpeg not found", channel_id, raw_output="ffmpeg not found")
            return
        except subprocess.TimeoutExpired:
            self.store.log_error(
                ErrorCode.CONVERT_FAILED.value,
                "Conversion timed out",
                channel_id,
                raw_output="Conversion process timed out after 900s",
            )
            return

        if result.returncode != 0:
            self.store.log_error(
                ErrorCode.CONVERT_FAILED.value,
                result.stderr.strip() or "Conversion failed",
                channel_id,
                raw_output=result.stderr.strip() or None,
                return_code=result.returncode,
            )
            return

        if config.delete_source_after_convert and source_path.exists():
            os.remove(source_path)
        
        # Only update file paths, do NOT touch status as it might be RECORDING again for a new session
        self.channel_service.update_status(
            channel_id,
            last_recorded_file=str(mp4_path),
            last_recorded_at=utc_now_iso(),
        )
        self.store.log_info("convert_completed", "Recording converted to MP4", channel_id, output=str(mp4_path))

    def _wait_for_recording_session(
        self,
        channel_id: str,
        process: subprocess.Popen[str],
        source_path: Path,
        mp4_path: Path,
        retry_attempt: int,
        *,
        session=None,
        resolved_source: ResolvedSource | None = None,
    ) -> None:
        stderr = ""
        if process.stderr:
            stderr = process.stderr.read()
        return_code = process.wait()

        with self._record_lock:
            self._active_processes.pop(channel_id, None)

        try:
            channel = self.channel_service.get_channel(channel_id)
        except KeyError:
            return

        next_status = Status.PAUSED if channel.paused else Status.IDLE
        self.channel_service.update_status(
            channel_id,
            status=next_status,
            active_pid=None,
            next_check_at=compute_next_check_at(channel_id, channel.poll_interval_seconds),
            last_error=None if return_code == 0 else channel.last_error,
        )

        session_registry = self._session_registry()
        if session is not None and session_registry is not None:
            session.active_pid = None

        if channel.paused and return_code != 0:
            if source_path.exists() and source_path.stat().st_size > 0:
                self._transition_session(
                    session,
                    RecordingPhase.CONVERTING,
                    "Recording stopped, starting conversion",
                    event_type="recording_session_converting",
                    source_path=str(source_path),
                    target_path=str(mp4_path),
                )
                self._convert_recording(channel_id, source_path, mp4_path)
                self._complete_session(session, message="Recording stopped and converted", outcome="aborted", source_path=str(source_path), target_path=str(mp4_path))
            else:
                self._complete_session(session, message="Recording stopped", outcome="aborted", source_path=str(source_path))
            return

        if return_code != 0:
            failure = self.recorder.platforms.get(channel.platform).map_recording_failure(stderr, return_code)
            category = classify_recording_failure(failure, room_status=resolved_source.room_status if resolved_source else None)
            adapter = self.recorder.platforms.get(channel.platform)
            should_reacquire = adapter.record_uses_resolved_source() and self.recorder.should_refresh_stream_source(stderr, source_path) and category in {
                FailureCategory.SOURCE_UNSTABLE,
                FailureCategory.NETWORK_TRANSIENT,
            }
            if should_reacquire:
                config = self.store.load_config()
                delay = self.recorder.compute_source_retry_delay(retry_attempt + 1)
                self._transition_session(
                    session,
                    RecordingPhase.SOURCE_RESOLUTION,
                    f"Retrying source after failure: {failure.message}",
                    event_type="recording_session_retry",
                    failure_category=category.value,
                    retry_attempt=retry_attempt + 1,
                    retry_delay_seconds=delay,
                )
                refreshed_source = self.recorder.acquire_resolved_source(
                    channel,
                    config,
                    session_id=session.id if session else channel_id,
                    retry_attempt=retry_attempt + 1,
                )
                if refreshed_source.stream_url and refreshed_source.stream_url != (resolved_source.stream_url if resolved_source else None):
                    self._attach_session_source(session, refreshed_source)
                    self._start_recording_session(
                        channel_id,
                        prepared_paths=(source_path, mp4_path),
                        retry_attempt=retry_attempt + 1,
                        session=session,
                        resolved_source=refreshed_source,
                    )
                    return
            if category == FailureCategory.PLATFORM_UNAVAILABLE:
                self.channel_service.update_status(
                    channel_id,
                    status=Status.PAUSED if channel.paused else Status.IDLE,
                    active_pid=None,
                    last_error=None,
                    next_check_at=compute_next_check_at(
                        channel_id,
                        channel.poll_interval_seconds,
                        failure_backoff_seconds(category.value),
                    ),
                )
                self._complete_session(session, message=failure.message, outcome="aborted", failure_category=category.value, raw_output=failure.raw_output, return_code=failure.return_code)
                return
            self.channel_service.update_status(
                channel_id,
                status=Status.ERROR,
                active_pid=None,
                last_error=failure.message,
                next_check_at=compute_next_check_at(
                    channel_id,
                    channel.poll_interval_seconds,
                    failure_backoff_seconds(category.value),
                ),
            )
            self._fail_session(
                session,
                phase=RecordingPhase.RECORDING,
                category=category,
                message=failure.message,
                raw_output=failure.raw_output,
                return_code=failure.return_code,
            )
            return

        self._transition_session(
            session,
            RecordingPhase.CONVERTING,
            "Recording finished, starting conversion",
            event_type="recording_session_converting",
            source_path=str(source_path),
            target_path=str(mp4_path),
        )
        self._convert_recording(channel_id, source_path, mp4_path)
        self._complete_session(session, message="Recording finished", outcome="completed", source_path=str(source_path), target_path=str(mp4_path))
