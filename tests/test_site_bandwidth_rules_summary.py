import unittest

from app.site_bandwidth_rules_summary import (
    SiteBandwidthRulesSummaryError, summarize_site_bandwidth_rules,
)


def rule(**overrides):
    row = {
        "id": "private-id", "name": "Private rule", "index": 7, "status": True,
        "sourceType": 0, "sourceIds": ["private-network"], "wanPortIds": ["wan-secret"],
        "upstreamBandwidth": 1234, "upstreamBandwidthUnit": 1,
        "downstreamBandwidth": 5678, "downstreamBandwidthUnit": 2, "mode": 0,
    }
    row.update(overrides)
    return row


class SiteBandwidthRulesSummaryTests(unittest.TestCase):
    def test_counts_activation_scope_mode_and_direction_units_without_values(self):
        result = summarize_site_bandwidth_rules(
            [rule(), rule(status=False, sourceType=1, mode=1,
                          upstreamBandwidthUnit=2, downstreamBandwidthUnit=1)], 2, 1, 10)
        self.assertEqual(result["activation_counts"], {
            "enabled": 1, "disabled": 1, "unknown": 0})
        self.assertEqual(result["source_type_counts"], {
            "network": 1, "ip_group": 1, "unknown": 0})
        self.assertEqual(result["mode_counts"], {
            "shared": 1, "individual": 1, "unknown": 0})
        self.assertEqual(result["bandwidth_unit_counts"]["upstream"], {
            "kbps": 1, "mbps": 1, "unknown": 0})
        self.assertFalse(result["partial"])
        for secret in ("private-id", "Private rule", "private-network", "wan-secret", "1234", "5678"):
            self.assertNotIn(secret, str(result))
        self.assertFalse(result["wan_configuration_inferred_from_policy_rules"])
        self.assertFalse(result["actual_traffic_inferred"])

    def test_unknown_codes_and_missing_fields_mark_partial(self):
        result = summarize_site_bandwidth_rules(
            [rule(sourceType=3, mode=4, upstreamBandwidthUnit=9)], 1, 1, 1)
        self.assertTrue(result["partial"])
        self.assertEqual(result["source_type_counts"]["unknown"], 1)
        self.assertEqual(result["mode_counts"]["unknown"], 1)
        self.assertEqual(result["bandwidth_unit_counts"]["upstream"]["unknown"], 1)
        self.assertTrue(summarize_site_bandwidth_rules([{}], 1, 1, 1)["partial"])

    def test_rejects_invalid_documented_types_and_ranges(self):
        for item in (rule(status=1), rule(sourceIds="private-network"),
                     rule(upstreamBandwidth=True), rule(downstreamBandwidth=10_000_000)):
            with self.subTest(item=item), self.assertRaises(SiteBandwidthRulesSummaryError):
                summarize_site_bandwidth_rules([item], 1, 1, 1)


if __name__ == "__main__":
    unittest.main()
