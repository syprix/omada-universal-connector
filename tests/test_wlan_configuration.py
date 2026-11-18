from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class WlanConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64,
            page_size=2, max_pages=2))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_ssid_list_uses_site_bound_opaque_refs_and_hides_names(self) -> None:
        rows = [{"id": "ssid-id-1", "ssidId": "ssid-id-1", "name": "private-wifi",
                 "description": True, "band": 3, "security": 3, "vlanId": 40,
                 "guestNetEnable": False, "broadcast": True, "vlanEnable": True,
                 "password": "secret"}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows):
            listed = self.client.list_ssids(self.site_ref)
        ref = listed["items"][0]["ssid_ref"]
        self.assertEqual(len(ref), 24)
        self.assertNotIn("private-wifi", str(listed))
        self.assertNotIn("ssid-id-1", str(listed))
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "id": "ssid-id-1", "name": "private-wifi", "ssidEnable": True,
                    "band": 7, "security": 5, "pmfMode": 1, "enable11r": True,
                    "guestNetEnable": False, "broadcast": True, "vlanEnable": True,
                    "vlanId": 40,
                    "vlanSetting": {"mode": 1, "customConfig": {
                        "customMode": 0, "lanNetworkId": "network-id-1", "vlanId": 40}},
                    "pskSetting": {"securityKey": "wifi-secret"},
                    "entSetting": {"radiusProfileId": "private-radius-profile"},
                    "apGroupIds": ["private-group-id"]}}) as request:
            result = self.client.read_ssid_configuration(self.site_ref, ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/wireless-network/ssids/ssid-id-1", token="token")
        self.assertEqual(result["data"], {"ssid_ref": ref, "enabled": True, "guest_enabled": False,
            "broadcast_enabled": True, "vlan_enabled": True, "fast_roaming_11r": True,
            "band": 7, "security_mode": 5, "pmf_mode": 1,
            "security_configuration_present": True,
            "security_credentials_present": True,
            "network_binding_ref": self.client._opaque_ref("network", "site_1:network-id-1"),
            "ap_group_binding_count": 1})
        for private in ("private-wifi", "ssid-id-1", "wifi-secret", "private-radius-profile",
                        "network-id-1", "vlanId", "private-group-id"):
            self.assertNotIn(private, str(result))
        self.assertNotIn("vlan_id", result["data"])
        self.assertNotIn(40, result["data"].values())

    def test_ssid_binding_reference_matches_current_network_inventory(self) -> None:
        network_rows = [{"id": "network-id-1", "name": "private-lan", "purpose": 1}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=network_rows):
            network_ref = self.client.list_networks(self.site_ref)["items"][0]["network_ref"]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=[{"id": "ssid-id-1"}]):
            ssid_ref = self.client.list_ssids(self.site_ref)["items"][0]["ssid_ref"]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "ssidEnable": True, "vlanSetting": {"customConfig": {
                        "lanNetworkId": "network-id-1"}}}}):
            detail = self.client.read_ssid_configuration(self.site_ref, ssid_ref)
        self.assertEqual(detail["data"]["network_binding_ref"], network_ref)
        self.assertNotIn("network-id-1", str(detail))

    def test_ssid_preflight_optional_fields_remain_unknown_when_missing(self) -> None:
        rows = [{"id": "ssid-id-1", "name": "private", "security": 3}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows):
            ref = self.client.list_ssids(self.site_ref)["items"][0]["ssid_ref"]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "ssidEnable": False, "security": 3, "pskSetting": None,
                    "vlanSetting": None, "apGroupIds": None}}):
            result = self.client.read_ssid_configuration(self.site_ref, ref)
        self.assertNotIn("security_configuration_present", result["data"])
        self.assertNotIn("security_credentials_present", result["data"])
        self.assertNotIn("network_binding_ref", result["data"])
        self.assertNotIn("ap_group_binding_count", result["data"])

    def test_ssid_preflight_rejects_malformed_nested_fields(self) -> None:
        ref = "d" * 24
        self.client._ssid_ids_by_site_ref[self.site_ref] = {ref: "ssid-id-1"}
        for result in (
            {"vlanSetting": {"customConfig": {"lanNetworkId": "raw/id"}}},
            {"apGroupIds": ["valid-id", 7]},
            {"pskSetting": {"securityKey": 7}},
        ):
            with self.subTest(result=result), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": result}), \
                    self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_ssid_configuration(self.site_ref, ref)

    def test_ssid_reference_is_site_bound_and_invalidated_on_site_refresh(self) -> None:
        rows = [{"id": "ssid-id-1", "name": "private", "band": 1, "security": 0}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows):
            ref = self.client.list_ssids(self.site_ref)["items"][0]["ssid_ref"]
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_ssid_configuration("b" * 24, ref)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=[]):
            self.client.list_sites()
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_ssid_configuration(self.site_ref, ref)

    def test_wlan_group_list_is_bounded_and_redacted(self) -> None:
        row = {"id": "wlan-group-id", "wlanId": "wlan-group-id", "name": "private-group",
               "primary": True, "clone": False, "site": "site_1", "cloneWlanId": "template-id",
               "resource": 2}
        payload = {"result": {"gridWlanGroup": {"data": [row], "totalRows": 1,
            "currentPage": 1, "currentSize": 1}, "maxSsids": 16}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload) as request:
            result = self.client.list_wlan_groups(self.site_ref)
        request.assert_called_once_with("GET", "/openapi/v2/ctrl/sites/site_1/wireless-network/wlans?page=1&pageSize=2", token="token")
        self.assertEqual(result["items"][0]["primary"], True)
        self.assertEqual(result["items"][0]["cloned"], False)
        self.assertEqual(result["items"][0]["resource_type"], 2)
        for private in ("private-group", "wlan-group-id", "template-id", "site_1"):
            self.assertNotIn(private, str(result))

    def test_bad_enum_and_non_get_path_are_rejected(self) -> None:
        ref = "c" * 24
        self.client._ssid_ids_by_site_ref[self.site_ref] = {ref: "ssid-id"}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"security": 9}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_ssid_configuration(self.site_ref, ref)
        good = "/openapi/v1/ctrl/sites/site_1/wireless-network/ssids/ssid-id"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("PATCH", good)
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", good + "?includeSecrets=true")


if __name__ == "__main__":
    unittest.main()
