from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_ssid_override_audit_summary import (
    ApSsidOverrideAuditError, summarize_ap_ssid_override_audit,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


def audit_grid() -> dict[str, object]:
    return {
        "totalRows": 2, "currentPage": 1, "currentSize": 2,
        "data": [
            {"globalSsid": "private-wlan", "oldSsidName": "old-name",
             "newSsidName": "new-name", "oldVlanId": "20", "newVlanId": "21",
             "passwordModified": True, "ssidNameModified": True,
             "vlanIdModified": False},
            {"globalSsid": "other-private-wlan", "oldSsidName": "other-old",
             "newSsidName": "other-new", "oldVlanId": "22", "newVlanId": "22",
             "passwordModified": False, "ssidNameModified": False,
             "vlanIdModified": True},
        ],
    }


class ApSsidOverrideAuditProjectionTests(unittest.TestCase):
    def test_returns_counts_and_omits_ssid_vlan_and_password_values(self) -> None:
        result = summarize_ap_ssid_override_audit(audit_grid())
        self.assertEqual(result["data"], {
            "reported_total_row_count": 2,
            "returned_row_count": 2,
            "password_modified_count": 1,
            "ssid_name_modified_count": 1,
            "vlan_id_modified_count": 1,
        })
        self.assertFalse(result["partial"])
        for secret in ("private-wlan", "old-name", "new-name", '"20"', '"21"'):
            self.assertNotIn(secret, repr(result))

    def test_missing_invalid_unknown_and_truncated_rows_are_partial(self) -> None:
        grid = audit_grid()
        grid["totalRows"] = 4
        grid["data"][0]["passwordModified"] = "yes"
        del grid["data"][1]["vlanIdModified"]
        grid["data"][1]["futureValue"] = "not returned"
        result = summarize_ap_ssid_override_audit(grid)
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["missing_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertTrue(result["truncated"])
        self.assertTrue(result["partial"])
        self.assertNotIn("not returned", repr(result))

    def test_rejects_invalid_grid_shape_and_page_metadata(self) -> None:
        for value in (None, [], {str(i): i for i in range(13)},
                      {"totalRows": 1, "currentPage": 2, "currentSize": 0, "data": []}):
            with self.subTest(value=type(value).__name__), \
                    self.assertRaises(ApSsidOverrideAuditError):
                summarize_ap_ssid_override_audit(value)


class ApSsidOverrideAuditClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.ap_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_internal"
        self.client._device_macs_by_site_ref[self.site_ref] = {
            self.ap_ref: "00:11:22:33:44:55"}

    def test_uses_inventoried_ap_and_fixed_default_window_page(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 0, "msg": "private controller text", "result": audit_grid()
                }) as request:
            result = self.client.read_ap_ssid_override_audit_summary(
                self.site_ref, self.ap_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_internal/audit-logs/"
            "00:11:22:33:44:55/ssid-overrides?page=1&pageSize=100", token="token")
        self.assertEqual(result["data"]["reported_total_row_count"], 2)
        self.assertNotIn("private controller text", repr(result))
        self.assertNotIn("private-wlan", repr(result))

    def test_unknown_ap_and_invalid_envelope_are_rejected(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
            self.client.read_ap_ssid_override_audit_summary(self.site_ref, "c" * 24)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "errorCode": 7, "msg": "private"}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_ap_ssid_override_audit_summary(self.site_ref, self.ap_ref)

    def test_request_guard_allows_only_the_fixed_page_offline(self) -> None:
        good = ("/openapi/v1/ctrl/sites/site_internal/audit-logs/"
                "00:11:22:33:44:55/ssid-overrides?page=1&pageSize=100")
        with patch.object(self.client, "_connection",
                           side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good, token="token")
        for path in (
            good.replace("/ctrl/", "/other/"),
            good.replace("?page=1&pageSize=100", ""),
            good.replace("pageSize=100", "pageSize=1000"),
            good + "&filters.times=[]",
        ):
            with self.subTest(path=path), \
                    self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", path, token="token")


if __name__ == "__main__":
    unittest.main()
