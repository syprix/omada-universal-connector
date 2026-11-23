import unittest

from app.site_ap_topology_clients import (
    SiteApTopologyClientsError, project_site_ap_topology_clients,
)


class SiteApTopologyClientsTests(unittest.TestCase):
    def test_counts_documented_connection_and_guest_flags_without_identity(self):
        result = project_site_ap_topology_clients([
            {"mac": "00:11:22:33:44:55", "name": "private", "type": "phone",
             "wireless": True, "guest": False, "uplinkApInfo": {"ssid": "private"}},
            {"mac": "00:11:22:33:44:66", "type": "client", "wireless": False,
             "guest": True},
            {"wireless": True, "guest": False},
        ])
        self.assertEqual(result["topology_client_count"], 3)
        self.assertEqual(result["by_connection"], {"wireless": 2, "wired": 1, "unknown": 0})
        self.assertEqual(result["type_present_count"], 2)
        self.assertEqual(result["type_missing_count"], 1)
        self.assertEqual(result["by_guest_flag"], {"guest": 1, "non_guest": 2, "unknown": 0})
        for secret in ("00:11:22:33:44:55", "private", "phone"):
            self.assertNotIn(secret, str(result))
        self.assertEqual(result["source_view"], "topology_snapshot")
        self.assertFalse(result["source_timestamp_provided"])
        self.assertFalse(result["roaming_history_included"])
        self.assertTrue(result["partial"])

    def test_unknown_optional_connection_is_partial(self):
        result = project_site_ap_topology_clients([{"type": "unclassified"}])
        self.assertTrue(result["partial"])
        self.assertEqual(result["by_connection"]["unknown"], 1)

    def test_rejects_invalid_documented_fields_and_oversized_lists(self):
        for rows in ([{"wireless": "yes"}], [{"guest": 1}], [None], ["x"] * 4097):
            with self.subTest(rows_type=type(rows[0]).__name__), \
                    self.assertRaises(SiteApTopologyClientsError):
                project_site_ap_topology_clients(rows)


if __name__ == "__main__":
    unittest.main()
