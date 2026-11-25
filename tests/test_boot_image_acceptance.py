"""Acceptance coverage for cluster-specific boot-image filename matching."""

from __future__ import annotations

import unittest

from moc_env.boot_image import image_is_specific
from moc_env.checks import _boot_image_state


class BootImageAcceptanceTest(unittest.TestCase):
    cluster = "oac-prod-workload1"
    hub = "oac-prod-infra"

    def assert_rule(self, url: object, expected: bool) -> None:
        with self.subTest(url=url):
            self.assertEqual(
                image_is_specific(url, self.cluster, self.hub), expected
            )
            state = _boot_image_state(url, self.cluster, self.hub)
            self.assertEqual(state == "declared_in_main", expected)

    def test_supported_cluster_and_hub_filename_forms(self) -> None:
        for filename in (
            "oac-prod-workload1.iso",
            "prod-workload1.iso",
            "oac-prod-workload1-agent.iso",
            "prod-workload1-agent-discovery.iso",
            "prod-workload1_agent.iso",
            "oac-prod-infra-agent.x86_64.iso",
            "prod-infra-agent-discovery.iso",
        ):
            self.assert_rule(f"http://10.2.0.82/boot/{filename}", True)

    def test_alias_must_start_filename_and_end_at_name_boundary(self) -> None:
        for filename in (
            "other-env-oac-prod-workload1-agent.iso",
            "oac-prod-workload10-agent.iso",
            "prod-workload1extra-agent.iso",
            "oac-prod-infrared-agent.iso",
        ):
            self.assert_rule(f"http://10.2.0.82/boot/{filename}", False)

    def test_generic_discovery_and_query_or_fragment_do_not_match(self) -> None:
        self.assert_rule(
            "http://10.2.0.82/boot/discovery.iso?cluster=oac-prod-workload1",
            False,
        )
        self.assert_rule(
            "http://10.2.0.82/boot/generic.iso#oac-prod-workload1",
            False,
        )

    def test_encoded_path_boundaries_do_not_smuggle_another_segment(self) -> None:
        self.assert_rule(
            "http://10.2.0.82/boot/other%2Foac-prod-workload1-agent.iso",
            False,
        )
        self.assert_rule(
            "http://10.2.0.82/boot/generic.iso%3Foac-prod-workload1",
            False,
        )

    def test_null_and_invalid_inputs_are_not_specific(self) -> None:
        for value in (
            None,
            "",
            42,
            b"oac-prod-workload1-agent.iso",
            "http://[invalid/cluster-agent.iso",
        ):
            self.assert_rule(value, False)


if __name__ == "__main__":
    unittest.main()
