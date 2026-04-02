from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.domain import (
    AppConfig,
    Channel,
    CommandType,
    Event,
    FailureCategory,
    Platform,
    RecordingSession,
    RecordingSessionPhase,
    RecordingSessionStatus,
    ResolvedSource,
    SessionEvent,
    SourceAuthMode,
)
from app.storage import JsonStore


class SqliteStoreTests(unittest.TestCase):
    def _build_store(self, tmpdir: str) -> JsonStore:
        base = Path(tmpdir)
        return JsonStore(
            config_path=base / "config.json",
            channels_path=base / "channels.json",
            event_db_path=base / "events.db",
            legacy_log_path=base / "events.jsonl",
        )

    def test_first_boot_imports_legacy_json_and_jsonl(self) -> None:
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            config = AppConfig(host="127.0.0.1", port=9000)
            channel = Channel(
                id="alice",
                username="alice",
                platform=Platform.CHATURBATE,
                url="https://chaturbate.com/alice",
                created_at=1,
            )
            (base / "config.json").write_text(json.dumps(config.model_dump(mode="json")), encoding="utf-8")
            (base / "channels.json").write_text(json.dumps([channel.model_dump(mode="json")]), encoding="utf-8")
            (base / "events.jsonl").write_text(
                json.dumps(
                    Event(
                        timestamp="2026-03-30T01:00:00+08:00",
                        level="INFO",
                        event_type="legacy_event",
                        channel_id="alice",
                        message="hello",
                        metadata={"legacy": True},
                    ).model_dump(mode="json")
                )
                + "\n",
                encoding="utf-8",
            )

            store = self._build_store(tmpdir)
            store.ensure_files()

            loaded_config = store.load_config()
            loaded_channels = store.load_channels()
            loaded_events = store.read_recent_events()

            self.assertEqual(loaded_config.host, "127.0.0.1")
            self.assertEqual(loaded_config.port, 9000)
            self.assertEqual(len(loaded_channels), 1)
            self.assertEqual(loaded_channels[0].id, "alice")
            self.assertEqual(len(loaded_events), 1)
            self.assertEqual(loaded_events[0]["event_type"], "legacy_event")
            self.assertEqual(loaded_events[0]["metadata"], {"legacy": True})

    def test_session_roundtrip_and_command_queue_work(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = self._build_store(tmpdir)
            store.ensure_files()

            session = RecordingSession(
                id="sess-1",
                channel_id="alice",
                status=RecordingSessionStatus.QUEUED,
                current_phase=RecordingSessionPhase.QUEUED,
                created_at="2026-03-30T01:00:00+08:00",
                updated_at="2026-03-30T01:00:00+08:00",
                metadata={"reason": "manual"},
            )
            created = store.create_session(session)
            self.assertEqual(created.id, "sess-1")
            self.assertEqual(created.status, RecordingSessionStatus.QUEUED)

            source = ResolvedSource(
                id="src-1",
                session_id="sess-1",
                resolver_tool="resolver",
                stream_url="https://example.com/live.m3u8",
                auth_mode=SourceAuthMode.COOKIES,
                metadata={"edge_region": "SIN"},
            )
            store.upsert_resolved_source(source)

            updated = store.update_session(
                "sess-1",
                status=RecordingSessionStatus.RECORDING,
                current_phase=RecordingSessionPhase.RECORDING,
                active_pid=1234,
                active_resolved_source_id="src-1",
            )
            self.assertEqual(updated.status, RecordingSessionStatus.RECORDING)
            self.assertEqual(updated.current_phase, RecordingSessionPhase.RECORDING)
            self.assertEqual(updated.active_resolved_source_id, "src-1")
            self.assertIsNotNone(updated.active_resolved_source)
            self.assertEqual(updated.active_resolved_source.stream_url, "https://example.com/live.m3u8")

            event_id = store.append_session_event(
                SessionEvent(
                    session_id="sess-1",
                    timestamp="2026-03-30T01:00:01+08:00",
                    phase=RecordingSessionPhase.RECORDING,
                    level="INFO",
                    event_type="recording_started",
                    message="Recording started",
                    failure_category=None,
                    metadata={"pid": 1234},
                )
            )
            self.assertGreater(event_id, 0)
            session_events = store.read_session_events("sess-1")
            self.assertEqual(len(session_events), 1)
            self.assertEqual(session_events[0].event_type, "recording_started")

            active_sessions = store.read_active_sessions()
            self.assertEqual(len(active_sessions), 1)

            command_id = store.enqueue_command(CommandType.CHECK, "alice", reason="manual_check")
            pending = store.claim_pending_commands()
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0].id, command_id)
            store.complete_command(command_id)
            self.assertEqual(store.claim_pending_commands(), [])

            final = store.update_session(
                "sess-1",
                status=RecordingSessionStatus.COMPLETED,
                current_phase=RecordingSessionPhase.FINALIZING,
                ended_at="2026-03-30T01:30:00+08:00",
                final_failure_category=FailureCategory.UNKNOWN,
                final_failure_message=None,
            )
            self.assertEqual(final.status, RecordingSessionStatus.COMPLETED)
            self.assertEqual(store.count_sessions(status=RecordingSessionStatus.COMPLETED), 1)
            self.assertEqual(store.count_session_events("sess-1"), 1)

    def test_log_helpers_append_structured_events(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = self._build_store(tmpdir)
            store.ensure_files()

            store.log_info("scheduler_started", "Scheduler service starting...", pid=1234)
            store.log_error("RECORDER_EXITED", "Recording stalled, recovering state", "alice", pid=5678, raw_output=None)

            events = store.read_recent_events(limit=10)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["level"], "ERROR")
            self.assertEqual(events[0]["event_type"], "RECORDER_EXITED")
            self.assertEqual(events[0]["channel_id"], "alice")
            self.assertEqual(events[0]["metadata"], {"pid": 5678})
            self.assertEqual(events[1]["level"], "INFO")
            self.assertEqual(events[1]["metadata"], {"pid": 1234})


if __name__ == "__main__":
    unittest.main()
