import unittest
from app.site_policy_route_summary import (
    SitePolicyRouteSummaryError, summarize_site_policy_routes,
)


class SitePolicyRouteSummaryTests(unittest.TestCase):
    def test_counts_known_policy_fields_without_identifiers_or_addresses(self):
        result = summarize_site_policy_routes([
            {"id": "secret-id", "index": 3, "name": "private-name", "status": True,
             "sourceType": 0, "sourceIds": ["source-id"], "destinationType": 2,
             "destinationIds": ["destination-id"], "interfaceType": 4,
             "wanPortIds": ["wan-id"], "vpnIds": [], "virtualWanIds": [],
             "interfaceId": "interface-id", "backupInterface": False},
            {"index": 4, "status": False, "sourceType": 1, "sourceIds": [],
             "destinationType": 1, "destinationIds": [], "interfaceType": 0,
             "wanPortIds": [], "vpnIds": [], "virtualWanIds": [],
             "backupInterface": False},
        ])
        self.assertEqual(result["summary"]["by_enabled"], {"false": 1, "true": 1})
        self.assertEqual(result["summary"]["by_source_type"], {"ip_group": 1, "network": 1})
        self.assertEqual(result["summary"]["reference_occurrences"],
                         {"destination": 1, "interface": 1, "source": 1, "wan": 1})
        serialized = str(result)
        for secret in ("secret-id", "private-name", "source-id", "destination-id", "wan-id"):
            self.assertNotIn(secret, serialized)
        self.assertIn("precedence semantics are not documented", result["ordering"])

    def test_unknown_values_and_duplicate_order_are_partial(self):
        result = summarize_site_policy_routes([
            {"index": 2, "status": "true", "sourceType": 99, "destinationType": 0,
             "interfaceType": 77, "sourceIds": "bad"},
            {"index": 2, "status": True, "sourceType": 0, "destinationType": 0,
             "interfaceType": 0},
        ])
        self.assertTrue(result["partial"])
        self.assertFalse(result["summary"]["indices_unique"])
        self.assertEqual(result["summary"]["invalid_rows"], 1)
        self.assertEqual(result["summary"]["invalid_fields"], 1)

    def test_row_limit(self):
        with self.assertRaises(SitePolicyRouteSummaryError):
            summarize_site_policy_routes([{}] * 10001)


if __name__ == "__main__":
    unittest.main()
