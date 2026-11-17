#!/usr/bin/env python3
"""Regenerate deterministic text/Markdown status test fixtures, without IO to GitHub."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from test_cli import CliDispatchTest
from fakes import FakeGitHubClient, FullyConfiguredFakeGitHubClient, MultiWorkloadFakeGitHubClient
from generate_sample_reports import FIXED_CLOCK


def main():
    case = CliDispatchTest()
    case.setUp()
    try:
        for output_format, extension in (("text", "txt"), ("markdown", "md")):
            for name, environment, client, flags in (
                ("environment-gaps", "bu-ist-demo", FakeGitHubClient, []),
                ("fully-configured", "bu-ist-demo", FullyConfiguredFakeGitHubClient, []),
                ("hub-no-workload", "dizzy", MultiWorkloadFakeGitHubClient, []),
                ("details", "bu-ist-demo", FakeGitHubClient, ["--details"]),
                ("ascii", "bu-ist-demo", FakeGitHubClient, ["--ascii"]),
            ):
                code, output, _ = case.run_cli(
                    ["status", environment, "--format", output_format, "--no-prs", *flags],
                    client_class=client, clock=FIXED_CLOCK,
                )
                assert code == 0
                (ROOT / "tests/fixtures" / output_format / f"{name}.{extension}").write_text(output)
    finally:
        case.doCleanups()


if __name__ == "__main__":
    main()
