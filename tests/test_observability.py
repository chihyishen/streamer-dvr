from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from app.common.observability import emit_event_log
from app.domain import Event


class ObservabilityTests(unittest.TestCase):
    def _event(self, metadata: dict[str, object]) -> Event:
        return Event(
            timestamp="2026-07-13T12:00:00+08:00",
            level="ERROR",
            event_type="recording_failed",
            channel_id="alice",
            message="capture failed",
            metadata=metadata,
        )

    def test_emit_event_log_recursively_redacts_credentials_and_url_queries(self) -> None:
        event = self._event(
            {
                "session_id": "sess-correlation-id",
                "source_url": "https://edge.example/live.m3u8?token=top-secret&expires=123#fragment",
                "source_candidates": [
                    "https://edge.example/one.m3u8?signature=secret-one",
                    {"url": "https://edge.example/two.m3u8?auth=secret-two"},
                ],
                "headers": {"Authorization": "Bearer secret", "x-api-token": "secret-three"},
                "cookie_file": "/tmp/private-cookies.txt",
                "detail": "retry https://edge.example/three.m3u8?token=secret-four now",
            }
        )

        output = io.StringIO()
        with redirect_stdout(output):
            emit_event_log(event)

        emitted = json.loads(output.getvalue())
        serialized = output.getvalue()
        self.assertEqual(emitted["metadata"]["session_id"], "sess-correlation-id")
        self.assertEqual(emitted["metadata"]["source_url"], "https://edge.example/live.m3u8")
        self.assertEqual(emitted["metadata"]["headers"]["Authorization"], "[REDACTED]")
        self.assertEqual(emitted["metadata"]["headers"]["x-api-token"], "[REDACTED]")
        self.assertEqual(emitted["metadata"]["cookie_file"], "[REDACTED]")
        self.assertNotIn("top-secret", serialized)
        self.assertNotIn("secret-one", serialized)
        self.assertNotIn("secret-two", serialized)
        self.assertNotIn("secret-three", serialized)
        self.assertNotIn("secret-four", serialized)

    def test_emit_event_log_swallows_secondary_output_failure(self) -> None:
        event = self._event({"return_code": 1})

        with patch("app.common.observability.sys.stdout.write", side_effect=OSError("closed pipe")):
            emit_event_log(event)


if __name__ == "__main__":
    unittest.main()
