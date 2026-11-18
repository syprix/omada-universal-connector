from __future__ import annotations

import unittest

from app.network_dhcp_capabilities import (
    FIELDS, NetworkDhcpCapabilitiesError, project_network_dhcp_capabilities,
)


class NetworkDhcpCapabilitiesTests(unittest.TestCase):
    def test_each_capability_is_strictly_projected(self) -> None:
        for source, target in FIELDS.items():
            with self.subTest(source=source):
                result = project_network_dhcp_capabilities({source: True})
                self.assertEqual(result["data"]["capabilities"], {target: True})
                self.assertEqual(result["data"]["present_count"], 1)
                self.assertEqual(result["data"]["missing_count"], 1)
                self.assertTrue(result["partial"])

    def test_projects_a_complete_response(self) -> None:
        result = project_network_dhcp_capabilities({
            "supportGetDhcpClientTable": True,
            "supportGetDhcpServerInfo": False,
        })
        self.assertEqual(result["data"]["capabilities"], {
            "get_dhcp_client_table": True,
            "get_dhcp_server_info": False,
        })
        self.assertFalse(result["partial"])

    def test_counts_invalid_and_unknown_fields_without_echoing_values(self) -> None:
        result = project_network_dhcp_capabilities({
            "supportGetDhcpClientTable": 1,
            "supportGetDhcpServerInfo": True,
            "privateField": "must-not-appear",
        })
        self.assertEqual(result["data"]["capabilities"], {"get_dhcp_server_info": True})
        self.assertEqual(result["data"]["invalid_count"], 1)
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertNotIn("privateField", repr(result))
        self.assertNotIn("must-not-appear", repr(result))

    def test_rejects_invalid_or_oversized_payloads(self) -> None:
        for value in (None, [], {str(index): True for index in range(17)}):
            with self.subTest(value=type(value).__name__), self.assertRaises(NetworkDhcpCapabilitiesError):
                project_network_dhcp_capabilities(value)


if __name__ == "__main__":
    unittest.main()
