from __future__ import annotations

import unittest
from unittest.mock import patch

from app.dhcp_pool_utilization import (
    DhcpPoolUtilizationError, project_dhcp_pool_utilization,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_REF = "a" * 24


class DhcpPoolUtilizationTests(unittest.TestCase):
    def test_projects_capacity_availability_and_leases_without_addresses(self):
        result = {"ranges": [
            {"startIp": "192.0.2.10", "endIp": "192.0.2.19", "availableIpNum": 2},
            {"startIp": "192.0.2.30", "endIp": "192.0.2.39", "availableIpNum": 0},
        ]}
        leases = [
            {"netId": "network-1", "status": 0, "type": 1,
             "ipAddress": "192.0.2.11", "macAddress": "00:11:22:33:44:55"},
            {"netId": "network-1", "status": 1, "type": 0,
             "ipAddress": "198.51.100.2", "macAddress": "00:11:22:33:44:66"},
        ]
        projected = project_dhcp_pool_utilization(result, leases, "network-1")
        self.assertEqual(projected["data"]["pool_capacity_address_count"], 20)
        self.assertEqual(projected["data"]["available_address_count"], 2)
        self.assertEqual(projected["data"]["non_available_address_count"], 18)
        self.assertEqual(projected["data"]["availability_percent"], 10.0)
        self.assertFalse(projected["data"]["pool_exhausted"])
        self.assertEqual(projected["data"]["dynamic_lease_count"], 1)
        self.assertEqual(projected["data"]["static_lease_count"], 1)
        self.assertEqual(projected["data"]["lease_pool_membership"],
                         "not_returned_by_source")
        self.assertFalse(projected["partial"])
        for raw in ("192.0.2.", "198.51.100.2", "00:11:22:33:44", "network-1"):
            self.assertNotIn(raw, str(projected))

    def test_only_zero_available_on_a_valid_nonempty_pool_is_depleted(self):
        full = project_dhcp_pool_utilization({"ranges": [
            {"startIp": "192.0.2.1", "endIp": "192.0.2.10", "availableIpNum": 0}],
        }, [], "network-1")
        self.assertTrue(full["data"]["pool_exhausted"])
        no_pool = project_dhcp_pool_utilization({"ranges": []}, [], "network-1")
        self.assertEqual(no_pool["data"]["pool_state"], "no_configured_ranges")
        self.assertIsNone(no_pool["data"]["pool_exhausted"])

    def test_overlapping_or_invalid_ranges_withhold_capacity(self):
        overlap = project_dhcp_pool_utilization({"ranges": [
            {"startIp": "192.0.2.1", "endIp": "192.0.2.20", "availableIpNum": 1},
            {"startIp": "192.0.2.10", "endIp": "192.0.2.15", "availableIpNum": 1},
        ]}, [], "network-1")
        self.assertIsNone(overlap["data"]["pool_capacity_address_count"])
        self.assertEqual(overlap["data"]["overlapping_range_count"], 1)
        invalid = project_dhcp_pool_utilization({"ranges": [
            {"startIp": "192.0.2.10", "endIp": "192.0.2.2", "availableIpNum": 1},
        ]}, [], "network-1")
        self.assertIsNone(invalid["data"]["pool_capacity_address_count"])
        self.assertTrue(invalid["partial"])

    def test_invalid_available_count_unknown_fields_and_bounds_are_reported(self):
        value = project_dhcp_pool_utilization({"ranges": [
            {"startIp": "192.0.2.1", "endIp": "192.0.2.5", "availableIpNum": 6,
             "extra": "private"}],
        }, [], "network-1")
        self.assertIsNone(value["data"]["available_address_count"])
        self.assertEqual(value["data"]["unknown_pool_field_count"], 1)
        self.assertTrue(value["partial"])
        with self.assertRaises(DhcpPoolUtilizationError):
            project_dhcp_pool_utilization({"ranges": [{}] * 65}, [], "network-1")

    def test_client_bundles_inventory_complete_lease_pages_and_exact_network_pools(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE_REF] = "site_1"
        network_rows = [
            {"id": "network-1", "name": "Private one", "vlan": 10},
            {"id": "network-2", "name": "Private two", "vlan": 20},
        ]
        lease_rows = [
            {"netId": "network-1", "type": 0, "status": 0,
             "macAddress": "00:11:22:33:44:55"},
            {"netId": "network-1", "type": 1, "status": 1,
             "macAddress": "00:11:22:33:44:66"},
            {"netId": "network-outside", "type": 1, "status": 0,
             "macAddress": "00:11:22:33:44:77"},
        ]

        def read_pages(path, _token):
            if path.endswith("/lan-networks"):
                return network_rows
            if path.endswith("/setting/service/dhcp/user-list"):
                return lease_rows
            raise AssertionError(path)

        requested = []

        def request(method, path, *, token=None):
            self.assertEqual(method, "GET")
            self.assertEqual(token, "test-token")
            requested.append(path)
            net_id = path.rsplit("/", 1)[-1].replace("network-", "network-")
            if path.endswith("network-1/dhcp-server-info"):
                return {"result": {"ranges": [
                    {"startIp": "192.0.2.1", "endIp": "192.0.2.10", "availableIpNum": 4}]}}
            if path.endswith("network-2/dhcp-server-info"):
                return {"result": {"ranges": []}}
            raise AssertionError((net_id, path))

        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_read_pages", side_effect=read_pages), \
                patch.object(client, "_request_json", side_effect=request):
            report = client.read_site_dhcp_pool_utilization(SITE_REF)
        self.assertEqual(report["summary"]["network_count"], 2)
        self.assertEqual(report["summary"]["pool_capacity_address_count"], 10)
        self.assertEqual(report["summary"]["available_address_count"], 4)
        self.assertEqual(report["summary"]["classified_lease_count"], 2)
        self.assertEqual(report["summary"]["unassociated_lease_count"], 1)
        self.assertTrue(report["partial"])
        self.assertEqual(len(requested), 2)
        for raw in ("network-1", "network-2", "Private one", "00:11:22:33:44", "192.0.2."):
            self.assertNotIn(raw, str(report))

    def test_client_rejects_unknown_site(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            client.read_site_dhcp_pool_utilization(SITE_REF)


if __name__ == "__main__":
    unittest.main()
