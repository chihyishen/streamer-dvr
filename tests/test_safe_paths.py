from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.common import UnsafePathError, safe_join, safe_segment


class SafeSegmentTests(unittest.TestCase):
    def test_rejects_empty(self) -> None:
        with self.assertRaises(UnsafePathError):
            safe_segment("")

    def test_rejects_traversal(self) -> None:
        for bad in ("..", ".", "foo/bar", "foo\\bar", "a\x00b"):
            with self.subTest(value=bad), self.assertRaises(UnsafePathError):
                safe_segment(bad)

    def test_trims_and_returns(self) -> None:
        self.assertEqual(safe_segment("  alice "), "alice")


class SafeJoinTests(unittest.TestCase):
    def test_stays_within_base(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            result = safe_join(base, "alice", "out.mp4")
            self.assertTrue(result.is_relative_to(base.resolve()))

    def test_rejects_traversal_segment(self) -> None:
        with TemporaryDirectory() as tmp, self.assertRaises(UnsafePathError):
            safe_join(Path(tmp), "..", "etc")

    def test_rejects_absolute_like_segment(self) -> None:
        with TemporaryDirectory() as tmp, self.assertRaises(UnsafePathError):
            safe_join(Path(tmp), "/etc/passwd")


if __name__ == "__main__":
    unittest.main()
