from __future__ import annotations

import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

from app.services.scheduler.service import SchedulerService


class SchedulerServiceRetentionTests(unittest.TestCase):
    def test_run_retention_logs_summary_when_rows_were_deleted(self) -> None:
        store = MagicMock()
        store.prune_retained_history.return_value = {
            "deleted_total": 7,
            "deleted_event_logs": 3,
            "deleted_session_logs": 2,
            "deleted_sessions": 2,
            "vacuumed": True,
        }
        scheduler = SchedulerService(store, MagicMock(), MagicMock())

        with patch("app.services.scheduler.service.time.monotonic", return_value=100.0):
            scheduler._run_retention_if_due(force=True)

        store.prune_retained_history.assert_called_once_with()
        store.log_info.assert_called_once_with(
            "log_retention_pruned",
            "Pruned retained logs and finished sessions",
            deleted_total=7,
            deleted_event_logs=3,
            deleted_session_logs=2,
            deleted_sessions=2,
            vacuumed=True,
        )

    def test_run_retention_logs_error_and_continues_on_failure(self) -> None:
        store = MagicMock()
        store.prune_retained_history.side_effect = RuntimeError("db busy")
        scheduler = SchedulerService(store, MagicMock(), MagicMock())

        with patch("app.services.scheduler.service.time.monotonic", return_value=100.0):
            scheduler._run_retention_if_due(force=True)

        store.log_error.assert_called_once()
        args, kwargs = store.log_error.call_args
        self.assertEqual(args[0], "log_retention_failed")
        self.assertEqual(args[1], "Failed to prune retained history: db busy")
        self.assertEqual(kwargs.get("error_type"), "RuntimeError")
        self.assertIn("RuntimeError: db busy", kwargs.get("traceback", ""))


class SchedulerServiceLoopIsolationTests(unittest.TestCase):
    def test_channel_tick_failure_does_not_abort_other_channels(self) -> None:
        store = MagicMock()
        channel_service = MagicMock()
        channel_a = MagicMock(id="a")
        channel_b = MagicMock(id="b")
        channel_service.list_channels.return_value = [channel_a, channel_b]

        scheduler = SchedulerService(store, channel_service, MagicMock())
        scheduler._run_retention_if_due = MagicMock()
        scheduler._process_commands = MagicMock()

        ticks: list[str] = []

        def fake_tick(channel) -> None:
            ticks.append(channel.id)
            if channel.id == "a":
                raise RuntimeError("boom")

        scheduler._tick_channel = fake_tick  # type: ignore[method-assign]

        def run_once(*_args, **_kwargs) -> None:
            scheduler._running = False

        scheduler._running = True
        with patch("app.services.scheduler.service.time.sleep", side_effect=run_once):
            scheduler._run_loop()

        self.assertEqual(ticks, ["a", "b"])  # "b" still processed after "a" raised
        store.log_error.assert_called_once()
        args, kwargs = store.log_error.call_args
        self.assertEqual(args[0], "scheduler_channel_tick_failed")
        self.assertEqual(args[2], "a")
        self.assertEqual(kwargs.get("error_type"), "RuntimeError")


if __name__ == "__main__":
    unittest.main()
