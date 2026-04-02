from __future__ import annotations

import unittest

from app.api.models import BootstrapResponse, ChannelListResponse, ChannelResponse, DeleteResponse, LogsResponse
from app.api.serializers import serialize_bootstrap, serialize_channel, serialize_event, serialize_logs_response
from app.domain import Channel, Platform, Status


class ApiModelsTests(unittest.TestCase):
    def test_channel_response_accepts_serialized_channel_payload(self) -> None:
        channel = Channel(
            id="alice",
            username="alice",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/alice",
            category="觀察",
            enabled=True,
            paused=False,
            poll_interval_seconds=180,
            filename_pattern="{streamer}_{started_at}.{ext}",
            created_at=1,
            status=Status.IDLE,
        )

        payload = serialize_channel(channel)

        parsed = ChannelResponse.model_validate(payload)
        self.assertEqual(parsed.id, "alice")
        self.assertEqual(parsed.status_label, "offline")

    def test_channel_list_response_accepts_items_key(self) -> None:
        channel = Channel(
            id="alice",
            username="alice",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/alice",
            category="觀察",
            enabled=True,
            paused=False,
            poll_interval_seconds=180,
            filename_pattern="{streamer}_{started_at}.{ext}",
            created_at=1,
            status=Status.IDLE,
        )

        payload = {"items": [serialize_channel(channel)]}
        parsed = ChannelListResponse.model_validate(payload)
        self.assertEqual(len(parsed.items), 1)
        self.assertEqual(parsed.items[0].id, "alice")

    def test_delete_response_accepts_ok_payload(self) -> None:
        parsed = DeleteResponse.model_validate({"ok": True})
        self.assertTrue(parsed.ok)

    def test_event_item_exposes_session_metadata(self) -> None:
        payload = serialize_event(
            {
                "timestamp": "2026-03-30T12:00:00+08:00",
                "level": "ERROR",
                "event_type": "SOURCE_URL_EXPIRED",
                "channel_id": "alice",
                "message": "Validated stream source returned 404",
                "metadata": {
                    "session_id": "sess-1",
                    "phase": "source_refresh",
                    "failure_category": "source_unstable",
                    "failure_message": "Validated stream source returned 404",
                    "source_status": "public",
                    "source_url": "https://edge.example/live.m3u8",
                    "source_candidate_id": "candidate-1",
                    "source_path_tail": "live.m3u8",
                },
            },
            {"alice": "alice"},
        )

        self.assertEqual(payload["session_id"], "sess-1")
        self.assertEqual(payload["failure_category"], "source_unstable")
        self.assertEqual(payload["phase"], "source_refresh")

    def test_bootstrap_response_includes_session_overview(self) -> None:
        channel = Channel(
            id="alice",
            username="alice",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/alice",
            category="觀察",
            enabled=True,
            paused=False,
            poll_interval_seconds=180,
            filename_pattern="{streamer}_{started_at}.{ext}",
            created_at=1,
            status=Status.RECORDING,
            active_pid=1234,
            last_recorded_at="2026-03-30T11:59:00+08:00",
        )
        payload = serialize_bootstrap(
            [channel],
            {"host": "0.0.0.0"},
            [
                {
                    "timestamp": "2026-03-30T12:00:00+08:00",
                    "level": "INFO",
                    "event_type": "recording_started",
                    "channel_id": "alice",
                    "message": "Streamer is live, recording started",
                    "metadata": {"session_id": "sess-1", "phase": "recording"},
                }
            ],
        )

        parsed = BootstrapResponse.model_validate(payload)
        self.assertEqual(parsed.session_overview.total_count, 1)
        self.assertEqual(parsed.active_sessions[0].channel_id, "alice")
        self.assertEqual(parsed.recent_sessions[0].phase, "recording")

    def test_bootstrap_filters_recent_events_to_refined_errors(self) -> None:
        channel = Channel(
            id="alice",
            username="alice",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/alice",
            category="觀察",
            enabled=True,
            paused=False,
            poll_interval_seconds=180,
            filename_pattern="{streamer}_{started_at}.{ext}",
            created_at=1,
            status=Status.IDLE,
        )
        payload = serialize_bootstrap(
            [channel],
            {"host": "0.0.0.0"},
            [
                {
                    "timestamp": "2026-03-30T12:00:00+08:00",
                    "level": "INFO",
                    "event_type": "recording_session_probing",
                    "channel_id": "alice",
                    "message": "Starting source resolution",
                    "metadata": {"session_id": "sess-1", "phase": "probing"},
                },
                {
                    "timestamp": "2026-03-30T12:00:05+08:00",
                    "level": "ERROR",
                    "event_type": "recording_session_failed",
                    "channel_id": "alice",
                    "message": "Validated stream source returned 404",
                    "metadata": {"session_id": "sess-1", "phase": "recording", "failure_category": "source_unstable"},
                },
            ],
        )

        parsed = BootstrapResponse.model_validate(payload)
        self.assertEqual(len(parsed.recent_events), 1)
        self.assertEqual(parsed.recent_events[0].failure_category, "source_unstable")

    def test_bootstrap_channels_expose_human_status_detail(self) -> None:
        channel = Channel(
            id="alice",
            username="alice",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/alice",
            category="觀察",
            enabled=True,
            paused=False,
            poll_interval_seconds=180,
            filename_pattern="{streamer}_{started_at}.{ext}",
            created_at=1,
            status=Status.IDLE,
        )
        payload = serialize_bootstrap(
            [channel],
            {"host": "0.0.0.0"},
            [
                {
                    "timestamp": "2026-03-30T12:00:00+08:00",
                    "level": "INFO",
                    "event_type": "recording_session_completed",
                    "channel_id": "alice",
                    "message": "Streamer unavailable (password protected)",
                    "summary": "Streamer unavailable (password protected)",
                    "metadata": {"room_status": "private"},
                }
            ],
        )

        channel_payload = payload["channels"][0]
        self.assertEqual(channel_payload["status_detail"], "Password protected")
        self.assertEqual(channel_payload["status_tone"], "neutral")

    def test_logs_recent_sessions_prioritize_active_and_failed_only(self) -> None:
        active_channel = Channel(
            id="alice",
            username="alice",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/alice",
            category="觀察",
            enabled=True,
            paused=False,
            poll_interval_seconds=180,
            filename_pattern="{streamer}_{started_at}.{ext}",
            created_at=1,
            status=Status.RECORDING,
            active_pid=1234,
            last_recorded_at="2026-03-30T11:59:00+08:00",
        )
        failed_channel = Channel(
            id="bob",
            username="bob",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/bob",
            category="觀察",
            enabled=True,
            paused=False,
            poll_interval_seconds=180,
            filename_pattern="{streamer}_{started_at}.{ext}",
            created_at=2,
            status=Status.ERROR,
            last_error="Validated stream source returned 404",
        )
        idle_channel = Channel(
            id="cara",
            username="cara",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/cara",
            category="觀察",
            enabled=True,
            paused=False,
            poll_interval_seconds=180,
            filename_pattern="{streamer}_{started_at}.{ext}",
            created_at=3,
            status=Status.IDLE,
        )
        payload = serialize_logs_response(
            [active_channel, failed_channel, idle_channel],
            [
                {
                    "timestamp": "2026-03-30T12:00:05+08:00",
                    "level": "ERROR",
                    "event_type": "recording_session_failed",
                    "channel_id": "bob",
                    "message": "Validated stream source returned 404",
                    "metadata": {"session_id": "sess-bob", "phase": "recording", "failure_category": "source_unstable"},
                }
            ],
            ["recording_session_failed"],
            total=1,
            limit=20,
            offset=0,
            has_next=False,
            recent_events=[
                {
                    "timestamp": "2026-03-30T12:00:05+08:00",
                    "level": "ERROR",
                    "event_type": "recording_session_failed",
                    "channel_id": "bob",
                    "message": "Validated stream source returned 404",
                    "metadata": {"session_id": "sess-bob", "phase": "recording", "failure_category": "source_unstable"},
                }
            ],
        )

        parsed = LogsResponse.model_validate(payload)
        self.assertEqual([session.channel_id for session in parsed.recent_sessions], ["alice", "bob"])

    def test_logs_response_includes_session_columns(self) -> None:
        channel = Channel(
            id="alice",
            username="alice",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/alice",
            category="觀察",
            enabled=True,
            paused=False,
            poll_interval_seconds=180,
            filename_pattern="{streamer}_{started_at}.{ext}",
            created_at=1,
            status=Status.ERROR,
            last_error="Validated stream source returned 404",
        )
        payload = serialize_logs_response(
            [channel],
            [
                {
                    "timestamp": "2026-03-30T12:00:00+08:00",
                    "level": "ERROR",
                    "event_type": "SOURCE_URL_EXPIRED",
                    "channel_id": "alice",
                    "message": "Validated stream source returned 404",
                    "metadata": {
                        "session_id": "sess-1",
                        "phase": "source_refresh",
                        "failure_category": "source_unstable",
                    },
                }
            ],
            ["SOURCE_URL_EXPIRED"],
            total=1,
            limit=20,
            offset=0,
            has_next=False,
            recent_events=[
                {
                    "timestamp": "2026-03-30T12:00:00+08:00",
                    "level": "ERROR",
                    "event_type": "SOURCE_URL_EXPIRED",
                    "channel_id": "alice",
                    "message": "Validated stream source returned 404",
                    "metadata": {
                        "session_id": "sess-1",
                        "phase": "source_refresh",
                        "failure_category": "source_unstable",
                    },
                }
            ],
        )

        parsed = LogsResponse.model_validate(payload)
        self.assertEqual(parsed.sessions[0].failure_category, "source_unstable")
        self.assertEqual(parsed.session_overview.source_issue_count, 1)
