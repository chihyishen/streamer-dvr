from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

from app.common import compute_next_check_at, failure_backoff_seconds, utc_now_iso
from app.domain import ErrorCode, Status
from app.services.session_core import FailureCategory, RecordingPhase, ResolvedSource, classify_recording_failure


class CaptureHandler:
    def __init__(self, store, channel_service, recorder, sessions, record_lock, active_processes, service) -> None:
        self.store = store
        self.channel_service = channel_service
        self.recorder = recorder
        self.sessions = sessions
        self._record_lock = record_lock
        self._active_processes = active_processes
        self.service = service

    def resolve_capture_artifact(self, source_path: Path) -> Path | None:
        candidates = [source_path, source_path.with_name(f"{source_path.name}.part")]
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.stat().st_size > 0:
                    return candidate
            except FileNotFoundError:
                continue
        return None

    def _retry_artifact_path(self, artifact_path: Path, retry_attempt: int) -> Path:
        suffix = "".join(artifact_path.suffixes)
        stem = artifact_path.name[: -len(suffix)] if suffix else artifact_path.name
        candidate = artifact_path.with_name(f"{stem}__retry{retry_attempt}{suffix}")
        collision_index = 1
        while candidate.exists():
            candidate = artifact_path.with_name(f"{stem}__retry{retry_attempt}_{collision_index}{suffix}")
            collision_index += 1
        return candidate

    def _preserve_retry_artifact(self, artifact_path: Path, retry_attempt: int) -> Path | None:
        preserved_path = self._retry_artifact_path(artifact_path, retry_attempt)
        try:
            artifact_path.replace(preserved_path)
        except FileNotFoundError:
            return None
        return preserved_path

    def _clear_missing_recording_state(self, channel, channel_id: str, source_path: Path) -> None:
        if channel.last_recorded_file != str(source_path):
            return
        self.channel_service.update_status(
            channel_id,
            last_recorded_file=None,
            last_recorded_at=None,
            last_recording_duration_seconds=None,
        )

    def _open_session(self, channel_id: str, *, trigger: str, metadata: dict[str, object] | None = None):
        return self.sessions.open(channel_id, trigger=trigger, metadata=metadata)

    def _attach_session_source(self, session, source: ResolvedSource) -> None:
        if session is not None:
            self.sessions.attach_source(session, source)

    def _transition_session(self, session, phase: RecordingPhase, message: str, *, event_type: str, level: str = "INFO", **metadata: object) -> None:
        if session is not None:
            self.sessions.transition(session, phase, message, event_type=event_type, level=level, **metadata)

    def _complete_session(self, session, *, message: str, outcome: str = "completed", **metadata: object) -> None:
        if session is not None:
            self.sessions.complete(session, message=message, outcome=outcome, **metadata)

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
        if session is not None:
            self.sessions.fail(session, phase=phase, category=category, message=message, event_type=event_type, **metadata)

    def start_recording(
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
                if resolved_source is not None:
                    category = resolved_source.failure_category or FailureCategory.UNKNOWN
                    fail_message = resolved_source.message
                else:
                    category = FailureCategory.UNKNOWN
                    fail_message = "Source resolution returned no result"
                next_status = Status.PAUSED if channel.paused else (Status.IDLE if category == FailureCategory.PLATFORM_UNAVAILABLE else Status.ERROR)
                self.channel_service.update_status(
                    channel_id,
                    status=next_status,
                    last_error=None if category == FailureCategory.PLATFORM_UNAVAILABLE else fail_message,
                    next_check_at=compute_next_check_at(
                        channel_id,
                        channel.poll_interval_seconds,
                        failure_backoff_seconds(category.value),
                    ),
                )
                if category == FailureCategory.PLATFORM_UNAVAILABLE:
                    self._complete_session(
                        session,
                        message=fail_message,
                        outcome="aborted",
                        source_fingerprint=getattr(resolved_source, "source_fingerprint", None),
                        source_url=getattr(resolved_source, "stream_url", None),
                        room_status=getattr(resolved_source, "room_status", None),
                    )
                else:
                    self._fail_session(
                        session,
                        phase=RecordingPhase.SOURCE_RESOLUTION,
                        category=category,
                        message=fail_message,
                        raw_output=getattr(resolved_source, "raw_output", None),
                        return_code=getattr(resolved_source, "return_code", None),
                        source_fingerprint=getattr(resolved_source, "source_fingerprint", None),
                        source_url=getattr(resolved_source, "stream_url", None),
                        room_status=getattr(resolved_source, "room_status", None),
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
                args=(channel_id, process, source_path, mp4_path, retry_attempt, session, resolved_source),
                daemon=True,
            ).start()

    def _wait_for_recording(
        self,
        channel_id: str,
        process: subprocess.Popen[str],
        source_path: Path,
        mp4_path: Path,
        retry_attempt: int,
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

        if session is not None:
            session.active_pid = None

        if channel.paused and return_code != 0:
            artifact_path = self.resolve_capture_artifact(source_path)
            if artifact_path is not None:
                self._transition_session(
                    session,
                    RecordingPhase.CONVERTING,
                    "Recording stopped, starting conversion",
                    event_type="recording_session_converting",
                    source_path=str(artifact_path),
                    target_path=str(mp4_path),
                )
                self.service._convert_recording(channel_id, artifact_path, mp4_path)
                self._complete_session(session, message="Recording stopped and converted", outcome="aborted", source_path=str(artifact_path), target_path=str(mp4_path))
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
                if config.keep_failed_source:
                    artifact_path = self.resolve_capture_artifact(source_path)
                    if artifact_path is not None:
                        preserved_path = self._preserve_retry_artifact(artifact_path, retry_attempt + 1)
                        if preserved_path is not None:
                            self.store.log_info(
                                "recording_artifact_preserved",
                                "Preserved partial recording before source retry",
                                channel_id,
                                source=str(artifact_path),
                                output=str(preserved_path),
                                retry_attempt=retry_attempt + 1,
                            )
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
                    self.service._start_recording(
                        channel_id,
                        prepared_paths=(source_path, mp4_path),
                        retry_attempt=retry_attempt + 1,
                        session=session,
                        resolved_source=refreshed_source,
                    )
                    return
            if category == FailureCategory.PLATFORM_UNAVAILABLE:
                artifact_path = self.resolve_capture_artifact(source_path)
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
                if artifact_path is not None:
                    self._transition_session(
                        session,
                        RecordingPhase.CONVERTING,
                        "Recording interrupted, salvaging partial file",
                        event_type="recording_session_converting",
                        source_path=str(artifact_path),
                        target_path=str(mp4_path),
                    )
                    self.service._convert_recording(channel_id, artifact_path, mp4_path, failed_recording=True)
                else:
                    self._clear_missing_recording_state(channel, channel_id, source_path)
                self._complete_session(
                    session,
                    message=failure.message,
                    outcome="aborted",
                    failure_category=category.value,
                    raw_output=failure.raw_output,
                    return_code=failure.return_code,
                    source_path=str(artifact_path) if artifact_path is not None else str(source_path),
                    target_path=str(mp4_path) if artifact_path is not None else None,
                )
                return
            artifact_path = self.resolve_capture_artifact(source_path)
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
            if artifact_path is not None:
                self._transition_session(
                    session,
                    RecordingPhase.CONVERTING,
                    "Recording failed, salvaging partial file",
                    event_type="recording_session_converting",
                    source_path=str(artifact_path),
                    target_path=str(mp4_path),
                )
                self.service._convert_recording(channel_id, artifact_path, mp4_path, failed_recording=True)
            else:
                self._clear_missing_recording_state(channel, channel_id, source_path)
            self._fail_session(
                session,
                phase=RecordingPhase.RECORDING,
                category=category,
                message=failure.message,
                raw_output=failure.raw_output,
                return_code=failure.return_code,
                source_path=str(artifact_path) if artifact_path is not None else str(source_path),
                target_path=str(mp4_path) if artifact_path is not None else None,
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
        duration_seconds = None
        if session is not None and hasattr(session, 'started_at') and session.started_at:
            try:
                from datetime import datetime, timezone
                started = datetime.fromisoformat(session.started_at)
                duration_seconds = int((datetime.now(started.tzinfo or timezone.utc) - started).total_seconds())
            except (ValueError, TypeError):
                duration_seconds = None
        self.service._convert_recording(channel_id, source_path, mp4_path, duration_seconds=duration_seconds)
        self._complete_session(session, message="Recording finished", outcome="completed", source_path=str(source_path), target_path=str(mp4_path))

    def convert_recording(
        self,
        channel_id: str,
        source_path: Path,
        mp4_path: Path,
        *,
        duration_seconds: int | None = None,
        failed_recording: bool = False,
    ) -> None:
        try:
            self.channel_service.get_channel(channel_id)
        except KeyError:
            return
        config = self.store.load_config()
        try:
            mp4_path.parent.mkdir(parents=True, exist_ok=True)
            command = self.recorder.build_convert_command(source_path, mp4_path)
            result = subprocess.run(command, capture_output=True, text=True, timeout=config.convert_timeout_seconds, check=False)
        except FileNotFoundError:
            self.store.log_error(ErrorCode.DEPENDENCY_MISSING.value, "ffmpeg not found", channel_id, raw_output="ffmpeg not found")
            return
        except subprocess.TimeoutExpired:
            self.store.log_error(
                ErrorCode.CONVERT_FAILED.value,
                "Conversion timed out",
                channel_id,
                raw_output=f"Probe process timed out after {config.convert_timeout_seconds}s",
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

        should_delete_source = config.delete_source_after_convert and (not failed_recording or not config.keep_failed_source)
        if should_delete_source and source_path.exists():
            os.remove(source_path)

        # Only update file paths, do NOT touch status as it might be RECORDING again for a new session
        self.channel_service.update_status(
            channel_id,
            last_recorded_file=str(mp4_path),
            last_recorded_at=utc_now_iso(),
            last_recording_duration_seconds=duration_seconds,
        )
        self.store.log_info("convert_completed", "Recording converted to MP4", channel_id, output=str(mp4_path))
