from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BANNER = "SAMPLE — generated from a synthetic fixture, not a live environment."


class SampleReportTest(unittest.TestCase):
    def test_every_sample_has_synthetic_banner(self) -> None:
        samples = ROOT / "docs" / "samples"
        files = [path for path in samples.iterdir() if path.is_file()]
        self.assertTrue(files)
        for path in files:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertTrue(
                    text.startswith(BANNER)
                    or text.startswith(f"# {BANNER}")
                )

    def test_reports_contains_no_stale_synthetic_environment(self) -> None:
        reports = ROOT / "reports"
        stale = [
            path
            for path in reports.iterdir()
            if path.is_file() and path.name.startswith("bu-ist-demo")
        ]
        self.assertEqual(stale, [])


if __name__ == "__main__":
    unittest.main()
