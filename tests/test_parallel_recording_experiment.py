from __future__ import annotations

import unittest
from pathlib import Path

from app.domain import Channel, Platform
from app.platform import ChaturbatePlatform
from scripts.parallel_recording_experiment import build_method_specs, summarize_packet_gaps


class ParallelRecordingExperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.platform = ChaturbatePlatform()
        self.channel = Channel(
            id="chan-1",
            username="germaine_jones",
            platform=Platform.CHATURBATE,
            url="https://chaturbate.com/germaine_jones",
            created_at=1,
        )

    def test_build_method_specs_includes_expected_parallel_variants(self) -> None:
        specs = build_method_specs(
            platform=self.platform,
            channel=self.channel,
            source_url="https://edge.example/live/playlist.m3u8",
            output_dir=Path("/tmp/parallel-experiment"),
            duration=600,
        )

        self.assertEqual(
            [spec.name for spec in specs],
            [
                "yt_dlp_room_page",
                "ffmpeg_source_matroska",
                "ffmpeg_source_mpegts",
            ],
        )
        self.assertTrue(str(specs[0].output_path).endswith(".mkv"))
        self.assertTrue(str(specs[1].output_path).endswith(".mkv"))
        self.assertTrue(str(specs[2].output_path).endswith(".ts"))
        self.assertIn("-f", specs[1].command)
        self.assertIn("matroska", specs[1].command)
        self.assertIn("-f", specs[2].command)
        self.assertIn("mpegts", specs[2].command)

    def test_summarize_packet_gaps_reports_large_audio_gap(self) -> None:
        summary = summarize_packet_gaps(
            [
                {"pts_time": "0.000000", "duration_time": "0.021333"},
                {"pts_time": "0.021333", "duration_time": "0.021333"},
                {"pts_time": "1.621333", "duration_time": "0.021333"},
            ],
            threshold_seconds=0.1,
        )

        self.assertEqual(summary["gap_count"], 1)
        self.assertEqual(summary["max_gap_seconds"], 1.579)
        self.assertEqual(summary["gaps_seconds"], [1.579])


if __name__ == "__main__":
    unittest.main()
