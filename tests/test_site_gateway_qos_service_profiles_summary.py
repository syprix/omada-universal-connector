import unittest

from app.site_gateway_qos_service_profiles_summary import (
    GatewayQosServiceProfilesError, summarize_gateway_qos_service_profiles,
)


class GatewayQosServiceProfilesSummaryTests(unittest.TestCase):
    def test_counts_documented_defaults_and_protocols_without_profile_details(self):
        result = summarize_gateway_qos_service_profiles([
            {"defaultProfile": True, "protocol": 0, "name": "private",
             "destStartPort": 443, "id": "secret"},
            {"defaultProfile": False, "protocol": 3},
            {"protocol": 99},
            {"defaultProfile": True},
        ])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["profile_count"], 4)
        self.assertEqual(result["default_profile_count"], 2)
        self.assertEqual(result["non_default_profile_count"], 1)
        self.assertEqual(result["unreported_default_flag_count"], 1)
        self.assertEqual(result["protocol_profile_counts"]["tcp"], 1)
        self.assertEqual(result["protocol_profile_counts"]["icmp"], 1)
        self.assertEqual(result["unclassified_protocol_count"], 1)
        self.assertEqual(result["unreported_protocol_count"], 1)
        for secret in ("private", "443", "secret", "99"):
            self.assertNotIn(secret, repr(result))

    def test_complete_counts_and_omissions_are_explicit(self):
        result = summarize_gateway_qos_service_profiles(
            [{"defaultProfile": False, "protocol": 2}], omitted_profile_count=3)
        self.assertEqual(result["profile_count"], 1)
        self.assertEqual(result["omitted_profile_count"], 3)
        self.assertTrue(result["partial"])
        self.assertEqual(result["protocol_profile_counts"]["tcp_udp"], 1)

    def test_rejects_invalid_rows(self):
        for row in (None, {"defaultProfile": "true"}, {"protocol": True}):
            with self.subTest(row=row), self.assertRaises(GatewayQosServiceProfilesError):
                summarize_gateway_qos_service_profiles([row])


if __name__ == "__main__":
    unittest.main()
