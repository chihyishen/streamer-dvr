from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.domain import ErrorCode, FailureCategory, RecordingSessionStatus
from app.platform import RecordingFailure
from app.services.session_core import RecordingPhase, RecordingSessionRegistry, ResolvedSource, classify_recording_failure
from app.storage import JsonStore


class SessionCorePersistenceTests(unittest.TestCase):
    def test_registry_persists_session_source_and_session_events(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = JsonStore(
                config_path=root / "config.json",
                channels_path=root / "channels.json",
                event_db_path=root / "events.db",
                legacy_log_path=root / "events.jsonl",
            )
            store.ensure_files()
            registry = RecordingSessionRegistry(store)

            session = registry.open("alice", trigger="probe", metadata={"reason": "test"})
            registry.transition(
                session,
                RecordingPhase.PROBING,
                "Starting source resolution",
                event_type="recording_session_probing",
            )
            registry.attach_source(
                session,
                ResolvedSource(
                    session_id=session.id,
                    stream_url="https://edge.example/live/playlist.m3u8",
                    message="Streamer is live",
                    room_status="public",
                    source_candidates=["https://edge.example/live/playlist.m3u8"],
                    source_fingerprint="public|playlist",
                ),
            )
            registry.fail(
                session,
                phase=RecordingPhase.RECORDING,
                category=FailureCategory.SOURCE_UNSTABLE,
                message="Validated stream source returned 404",
            )

            persisted = store.get_session(session.id)
            self.assertEqual(persisted.status, RecordingSessionStatus.FAILED)
            self.assertEqual(persisted.final_failure_category, FailureCategory.SOURCE_UNSTABLE)
            self.assertIsNotNone(persisted.active_resolved_source)
            assert persisted.active_resolved_source is not None
            self.assertEqual(persisted.active_resolved_source.stream_url, "https://edge.example/live/playlist.m3u8")
            events = store.read_session_events(session.id)
            self.assertGreaterEqual(len(events), 3)

    def test_registry_deduplicates_repeated_global_error_events(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = JsonStore(
                config_path=root / "config.json",
                channels_path=root / "channels.json",
                event_db_path=root / "events.db",
                legacy_log_path=root / "events.jsonl",
            )
            store.ensure_files()
            registry = RecordingSessionRegistry(store)

            first = registry.open("alice", trigger="probe", metadata={"reason": "test"})
            registry.fail(
                first,
                phase=RecordingPhase.SOURCE_RESOLUTION,
                category=FailureCategory.SOURCE_UNSTABLE,
                message="Validated stream source returned 404",
            )

            second = registry.open("alice", trigger="probe", metadata={"reason": "test"})
            registry.fail(
                second,
                phase=RecordingPhase.SOURCE_RESOLUTION,
                category=FailureCategory.SOURCE_UNSTABLE,
                message="Validated stream source returned 404",
            )

            self.assertEqual(store.count_events(channel_id="alice", level="ERROR"), 1)
            self.assertGreaterEqual(len(store.read_session_events(first.id)), 1)
            self.assertGreaterEqual(len(store.read_session_events(second.id)), 1)

    def test_registry_skips_global_events_for_probe_noise_lifecycle(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = JsonStore(
                config_path=root / "config.json",
                channels_path=root / "channels.json",
                event_db_path=root / "events.db",
                legacy_log_path=root / "events.jsonl",
            )
            store.ensure_files()
            registry = RecordingSessionRegistry(store)

            session = registry.open("alice", trigger="probe", metadata={"reason": "test"})
            registry.transition(
                session,
                RecordingPhase.PROBING,
                "Starting source resolution",
                event_type="recording_session_probing",
            )
            registry.transition(
                session,
                RecordingPhase.SOURCE_RESOLUTION,
                "Resolving",
                event_type="recording_session_source_resolution",
            )
            registry.complete(session, message="Probe complete", outcome="aborted")

            global_event_types = {item["event_type"] for item in store.read_recent_events(limit=20)}
            self.assertFalse(global_event_types & {
                "recording_session_started",
                "recording_session_probing",
                "recording_session_source_resolution",
                "recording_session_completed",
            })
            session_event_types = {item.event_type for item in store.read_session_events(session.id)}
            self.assertIn("recording_session_started", session_event_types)
            self.assertIn("recording_session_probing", session_event_types)
            self.assertIn("recording_session_source_resolution", session_event_types)
            self.assertIn("recording_session_completed", session_event_types)

    def test_registry_keeps_global_event_for_completed_probe_recording(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = JsonStore(
                config_path=root / "config.json",
                channels_path=root / "channels.json",
                event_db_path=root / "events.db",
                legacy_log_path=root / "events.jsonl",
            )
            store.ensure_files()
            registry = RecordingSessionRegistry(store)

            session = registry.open("alice", trigger="probe", metadata={"reason": "test"})
            registry.complete(session, message="Recording finished", outcome="completed")

            global_events = store.read_recent_events(limit=20)
            self.assertEqual([item["event_type"] for item in global_events], ["recording_session_completed"])

    def test_classify_recording_failure_treats_403_source_expired_as_source_unstable(self) -> None:
        category = classify_recording_failure(
            RecordingFailure(
                error_code=ErrorCode.SOURCE_URL_EXPIRED,
                message="Stream source expired (403/401)",
            ),
            room_status="public",
        )

        self.assertEqual(category, FailureCategory.SOURCE_UNSTABLE)


if __name__ == "__main__":
    unittest.main()
