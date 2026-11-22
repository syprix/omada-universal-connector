import unittest
from app.site_wan_qos_summary import SiteWanQosSummaryError, summarize_site_wan_qos


class SiteWanQosSummaryTests(unittest.TestCase):
    def test_counts_activation_and_only_exact_port_matches(self):
        result = summarize_site_wan_qos(
            [{"id": "secret-wan", "name": "Private port", "configured": True},
             {"id": "other-wan", "configured": False},
             {"id": "unknown-wan", "configured": None}],
            [{"id": "rule-secret", "wan": "secret-wan", "status": True,
              "direction": 2, "inBandwidth": 1000, "outBandwidth": 2000},
             {"wan": "missing-wan", "status": False, "direction": 1}],
        )
        self.assertEqual(result["by_configured"], {"false": 1, "true": 1, "unknown": 1})
        self.assertEqual(result["rules_with_exact_wan_match"], 1)
        self.assertEqual(result["rules_without_unique_wan_match"], 1)
        self.assertEqual(result["rules_by_enabled_status"], {"false": 1, "true": 1})
        for secret in ("secret-wan", "Private port", "rule-secret", "1000", "2000"):
            self.assertNotIn(secret, str(result))
        self.assertIn("not specified", result["bandwidth_units"])
        self.assertTrue(result["partial"])

    def test_duplicate_wan_identifiers_do_not_create_a_match(self):
        result = summarize_site_wan_qos(
            [{"id": "dup", "configured": True}, {"id": "dup", "configured": True}],
            [{"wan": "dup", "status": True, "direction": 0}],
        )
        self.assertEqual(result["rules_without_unique_wan_match"], 1)

    def test_limits(self):
        with self.assertRaises(SiteWanQosSummaryError):
            summarize_site_wan_qos([{}] * 10001, [])


if __name__ == "__main__":
    unittest.main()
