import unittest

from app.network_dhcp_server_info import (
    MAX_RANGES, NetworkDhcpServerInfoError, project_network_dhcp_server_info,
)


class NetworkDhcpServerInfoTests(unittest.TestCase):
    def test_projects_every_documented_field_without_returning_addresses(self):
        result = project_network_dhcp_server_info({"ranges": [
            {"startIp": "192.0.2.10", "endIp": "192.0.2.20", "availableIpNum": 7},
            {"startIp": "198.51.100.10", "endIp": "198.51.100.20", "availableIpNum": 4},
        ]})
        self.assertEqual(result, {"data": {
            "range_count": 2, "included_range_count": 2,
            "omitted_range_count": 0, "available_ip_count": 11,
            "available_ip_values_count": 2, "invalid_range_count": 0,
            "unknown_field_count": 0, "missing_ranges_count": 0,
        }, "partial": False})

    def test_empty_inventory_is_valid_and_missing_ranges_is_partial(self):
        self.assertFalse(project_network_dhcp_server_info({"ranges": []})["partial"])
        missing = project_network_dhcp_server_info({})
        self.assertTrue(missing["partial"])
        self.assertEqual(missing["data"]["missing_ranges_count"], 1)

    def test_invalid_values_and_unknown_fields_are_counted(self):
        result = project_network_dhcp_server_info({"ranges": [
            {"startIp": 1, "endIp": "192.0.2.2", "availableIpNum": True, "extra": "private"},
        ], "extra": "private"})
        data = result["data"]
        self.assertTrue(result["partial"])
        self.assertEqual(data["invalid_range_count"], 1)
        self.assertEqual(data["unknown_field_count"], 2)
        self.assertEqual(data["available_ip_count"], 0)

    def test_bounds_rows_and_rejects_wrong_container_types(self):
        rows = [{"startIp": "", "endIp": "", "availableIpNum": 1} for _ in range(MAX_RANGES + 3)]
        result = project_network_dhcp_server_info({"ranges": rows})
        self.assertEqual(result["data"]["included_range_count"], MAX_RANGES)
        self.assertEqual(result["data"]["omitted_range_count"], 3)
        self.assertTrue(result["partial"])
        unknown = project_network_dhcp_server_info({"x": 1})
        self.assertTrue(unknown["partial"])
        self.assertEqual(unknown["data"]["unknown_field_count"], 1)
        for value in (None, [], {"ranges": {}}, {"ranges": "invalid"}):
            with self.subTest(value=type(value).__name__), self.assertRaises(NetworkDhcpServerInfoError):
                project_network_dhcp_server_info(value)


if __name__ == "__main__":
    unittest.main()
