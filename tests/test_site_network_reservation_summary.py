from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_network_reservation_summary import (
    SiteNetworkReservationError, project_site_network_reservations)
from app.site_dhcp_reservation_summary import (
    SiteDhcpReservationError, project_site_dhcp_reservations)


class SiteNetworkReservationProjectorTests(unittest.TestCase):
    def test_projects_counts_and_discards_all_private_values(self):
        result = {"networks": [
            {"id": "private-network-id", "name": "private-network-name", "type": "LAN",
             "serverDevices": [
                 {"name": "private-device", "mac": "private-mac", "model": "private-model",
                  "ranges": [{"ipaddrStart": "10.0.0.2", "ipaddrEnd": "10.0.0.9"}],
                  "dhcpServerEnable": True, "dhcpSettingsAuto": False,
                  "supportDhcpReservation": True},
                 {"name": "private-device-2", "ranges": [],
                  "dhcpServerEnable": False, "dhcpSettingsAuto": True,
                  "supportDhcpReservation": False},
             ]},
        ]}
        projected = project_site_network_reservations(result)
        self.assertEqual(projected["data"], {
            "eligible_network_count": 1, "dhcp_server_count": 2,
            "dhcp_enabled_server_count": 1, "auto_configured_server_count": 1,
            "reservation_supported_server_count": 1, "configured_range_count": 1,
        })
        self.assertFalse(projected["partial"])
        self.assertNotIn("private", repr(projected))

    def test_missing_values_stay_unknown(self):
        projected = project_site_network_reservations({
            "networks": [{"serverDevices": [{"ranges": []}]}]})
        self.assertIsNone(projected["data"]["dhcp_enabled_server_count"])
        self.assertIsNone(projected["data"]["auto_configured_server_count"])
        self.assertIsNone(projected["data"]["reservation_supported_server_count"])
        self.assertEqual(projected["data"]["configured_range_count"], 0)
        self.assertTrue(projected["partial"])

    def test_invalid_and_unknown_values_are_reported_without_echo(self):
        projected = project_site_network_reservations({
            "networks": [{"serverDevices": [{"dhcpServerEnable": "yes",
                                              "dhcpSettingsAuto": True,
                                              "supportDhcpReservation": False,
                                              "ranges": [], "secretField": "secret-value"}]}]})
        self.assertGreater(projected["invalid_field_count"], 0)
        self.assertGreater(projected["unknown_field_count"], 0)
        self.assertNotIn("secret", repr(projected))
        self.assertTrue(projected["partial"])

    def test_rejects_invalid_envelope(self):
        for result in (None, [], {str(i): i for i in range(17)}):
            with self.assertRaises(SiteNetworkReservationError):
                project_site_network_reservations(result)

        malformed = project_site_network_reservations({"networks": "not-a-list"})
        self.assertEqual(malformed["data"]["eligible_network_count"], 0)
        self.assertGreater(malformed["invalid_field_count"], 0)


class SiteNetworkReservationClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_fixed_site_path_without_query_and_projects_response(self):
        payload = {"result": {"networks": [{"id": "private-id", "name": "private-name",
                    "serverDevices": [{"ranges": [], "dhcpServerEnable": True,
                                        "dhcpSettingsAuto": True,
                                        "supportDhcpReservation": True}]}]}}
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_site_network_reservation_summary(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/networks/server-for-reservation",
            token="test-token")
        self.assertEqual(result["data"]["dhcp_server_count"], 1)
        self.assertNotIn("private", repr(result))

    def test_path_guard_and_unknown_site(self):
        self.assertTrue(self.client._site_network_reservation_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/networks/server-for-reservation"))
        self.assertFalse(self.client._site_network_reservation_request_valid(
            "/openapi/v1/other/sites/site_internal/networks/server-for-reservation"))
        self.assertFalse(self.client._site_network_reservation_request_valid(
            "/openapi/v1/ctrl/sites/site_internal/networks/server-for-reservation?page=1"))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_site_network_reservation_summary("7" * 24)


def reservation_page(page, total, rows):
    return {"totalRows": total, "currentPage": page,
            "currentSize": len(rows), "data": rows}


class SiteDhcpReservationProjectorTests(unittest.TestCase):
    def test_counts_reservations_and_redacts_row_values(self):
        rows = [
            {"id": "private-id", "description": "private-description", "netName": "private-net",
             "mac": "private-mac", "ip": "192.0.2.30", "status": True, "type": 0,
             "options": [{"value": "private-option"}]},
            {"id": "private-id-2", "netName": "private-net", "mac": "private-mac-2",
             "ip": "192.0.2.31", "status": False, "type": 1},
        ]
        result = project_site_dhcp_reservations([reservation_page(1, 2, rows)])
        self.assertEqual(result["data"], {
            "reported_total_reservation_count": 2, "returned_reservation_count": 2,
            "valid_reservation_record_count": 2, "enabled_reservation_count": 1,
            "disabled_reservation_count": 1, "device_reservation_count": 1,
            "client_reservation_count": 1, "other_type_reservation_count": 0,
            "pages_read": 1, "truncated": False,
        })
        self.assertFalse(result["partial"])
        for value in ("private-id", "private-description", "private-net", "private-mac",
                      "192.0.2.30", "private-option"):
            self.assertNotIn(value, repr(result))

    def test_missing_fields_unknown_types_and_truncation(self):
        partial = project_site_dhcp_reservations([reservation_page(1, 1, [{"id": "secret"}])])
        self.assertIsNone(partial["data"]["enabled_reservation_count"])
        self.assertIsNone(partial["data"]["device_reservation_count"])
        self.assertTrue(partial["partial"])
        full_pages = [reservation_page(i, 900, [{"status": True, "type": 8}] * 100)
                      for i in range(1, 6)]
        capped = project_site_dhcp_reservations(full_pages)
        self.assertEqual(capped["data"]["returned_reservation_count"], 500)
        self.assertTrue(capped["data"]["truncated"])

    def test_rejects_unbounded_pages(self):
        for pages in (None, [], [reservation_page(i, 0, []) for i in range(6)]):
            with self.assertRaises(SiteDhcpReservationError):
                project_site_dhcp_reservations(pages)


class SiteDhcpReservationClientTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "8" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"

    def test_reads_only_fixed_page_and_returns_redacted_counts(self):
        payload = {"result": reservation_page(1, 1, [{"mac": "private-mac", "ip": "10.0.0.4",
                   "status": True, "type": 0}])}
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.read_site_dhcp_reservation_summary(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/setting/service/dhcp?page=1&pageSize=100",
            token="test-token")
        self.assertEqual(result["data"]["enabled_reservation_count"], 1)
        self.assertNotIn("private-mac", repr(result))
        self.assertNotIn("10.0.0.4", repr(result))

    def test_caps_the_fixed_read_at_five_pages(self):
        payloads = [{"result": reservation_page(i, 900,
                    [{"status": True, "type": 0}] * 100)} for i in range(1, 6)]
        with patch.object(self.client, "_access_token", return_value="test-token"), \
                patch.object(self.client, "_request_json", side_effect=payloads) as request:
            result = self.client.read_site_dhcp_reservation_summary(self.site_ref)
        self.assertEqual(request.call_count, 5)
        self.assertEqual(request.call_args_list[0].args[1],
                         "/openapi/v1/ctrl/sites/site_internal/setting/service/dhcp?page=1&pageSize=100")
        self.assertEqual(request.call_args_list[-1].args[1],
                         "/openapi/v1/ctrl/sites/site_internal/setting/service/dhcp?page=5&pageSize=100")
        self.assertEqual(result["data"]["returned_reservation_count"], 500)
        self.assertTrue(result["data"]["truncated"])

    def test_path_guard_rejects_unapproved_controller_and_queries(self):
        valid = "/openapi/v1/ctrl/sites/site_internal/setting/service/dhcp?page=1&pageSize=100"
        self.assertTrue(self.client._site_dhcp_reservations_request_valid(valid))
        self.assertFalse(self.client._site_dhcp_reservations_request_valid(
            valid.replace("/ctrl/", "/other/")))
        self.assertFalse(self.client._site_dhcp_reservations_request_valid(valid + "&searchKey=x"))


if __name__ == "__main__":
    unittest.main()
