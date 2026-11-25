"""Preserve falsey manual defaults instead of displaying a missing value."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from moc_env.chart_values import (
    ManualDocumentation,
    ManualTopic,
    ManualVariable,
    render_chart_values_markdown,
)
from moc_env.observed import read_chart_values_reference_observation
from test_chart_values import ValuesClient


class ChartValuesDefaultsRegressionTest(unittest.TestCase):
    def test_tracked_false_defaults_are_rendered(self) -> None:
        observation = read_chart_values_reference_observation(ValuesClient())
        rendered = render_chart_values_markdown(observation)
        for key in ("dns.enabled", "dns.autoGenerate"):
            self.assertIn(f"| `{key}` | Optional | `False` |", rendered)

    def test_default_takes_precedence_unless_it_is_none(self) -> None:
        observation = read_chart_values_reference_observation(ValuesClient())
        for default, fallback, expected in (
            (False, "fallback", "False"),
            (0, "fallback", "0"),
            ("", "fallback", ""),
            (None, "fallback", "fallback"),
            (None, "", ""),
            (None, None, "—"),
        ):
            with self.subTest(default=default, fallback=fallback):
                variable = ManualVariable(
                    key="example.key",
                    title="Example",
                    group="Defaults",
                    required=False,
                    definition="An example setting.",
                    default=default,
                    fallback=fallback,
                )
                manual = ManualDocumentation(
                    sources={},
                    topics=(ManualTopic("example", "Example", "Defaults.", (variable,)),),
                )
                with patch("moc_env.chart_values.load_chart_values_manual", return_value=manual):
                    rendered = render_chart_values_markdown(observation)
                self.assertIn(f"| `example.key` | Optional | `{expected}` |", rendered)
