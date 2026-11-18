from __future__ import annotations

import unittest
from unittest.mock import call, patch

from app.ap_port_vlans import ApPortVlansError, summarize_ap_port_vlans


class ApPortVlansProjectionTests(unittest.TestCase):
    def test_keeps_vlan_ids_and_port_counts_but_redacts_network_identity(self):
        result = summarize_ap_port_vlans({
            "totalRows": 2, "currentPage": 1, "currentSize": 2,
            "data": [
                {"localVlanId": 10, "localVlanNetworkId": "network-secret",
                 "name": "private name", "ipaddr": "10.0.0.1",
                 "nativePort": ["port-1"], "tagPort": ["port-2", "port-3"],
                 "untagPort": []},
                {"localVlanId": 10, "nativePort": [], "tagPort": [],
                 "untagPort": ["port-4"]},
            ],
        })
        self.assertEqual(result["vlan_id_counts"], {10: 2})
        self.assertEqual(result["port_counts"], {
            "nativePort": 1, "tagPort": 2, "untagPort": 1,
        })
        self.assertEqual(result["redacted_field_count"], 3)
        for secret in ("network-secret", "private name", "10.0.0.1", "port-1"):
            self.assertNotIn(secret, repr(result))
        self.assertFalse(result["partial"])

    def test_unknown_and_invalid_values_are_counted_without_disclosure(self):
        result = summarize_ap_port_vlans({
            "totalRows": 1, "currentPage": 1, "currentSize": 1,
            "data": [{"localVlanId": True, "nativePort": "secret-port",
                      "vendorField": "private-extension"}],
        })
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["invalid_row_or_field_count"], 2)
        self.assertNotIn("private-extension", repr(result))
        self.assertNotIn("secret-port", repr(result))

    def test_rejects_malformed_grid_and_oversized_values(self):
        for value in (None, [], {"totalRows": True, "currentPage": 1,
                                 "currentSize": 0, "data": []},
                      {"totalRows": 10_001, "currentPage": 1,
                       "currentSize": 0, "data": []}):
            with self.subTest(value=repr(value)[:40]):
                with self.assertRaises(ApPortVlansError):
                    summarize_ap_port_vlans(value)
        overlong = summarize_ap_port_vlans({
            "totalRows": 1, "currentPage": 1, "currentSize": 1,
            "data": [{"nativePort": ["x" * 65]}],
        })
        self.assertEqual(overlong["invalid_row_or_field_count"], 1)
        self.assertTrue(overlong["partial"])


class ApPortVlansClientTests(unittest.TestCase):
    def test_fixed_paginated_route_is_bound_to_inventoried_ap(self):
        from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site-1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA-BB-CC-DD-EE-FF"}
        payloads = [
            {"errorCode": 0, "result": {"totalRows": 2, "currentPage": 1,
             "currentSize": 1000, "data": [{"localVlanId": 7,
             "name": "private-name", "nativePort": ["port"]}]}},
            {"errorCode": 0, "result": {"totalRows": 2, "currentPage": 2,
             "currentSize": 1, "data": [{"localVlanId": 7, "tagPort": ["secret-port"]}]}},
        ]
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", side_effect=payloads) as request:
            result = client.read_ap_port_vlans(site_ref, ap_ref)
        self.assertEqual(request.call_args_list, [
            call("GET", "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/"
                 "port-vlans?page=1&pageSize=1000", token="token"),
            call("GET", "/openapi/v1/ctrl/sites/site-1/aps/AA-BB-CC-DD-EE-FF/"
                 "port-vlans?page=2&pageSize=1000", token="token"),
        ])
        self.assertEqual(result["resource"], "ap_port_vlans")
        self.assertEqual(result["vlan_id_counts"], {7: 2})
        self.assertNotIn("private-name", repr(result))
        with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
            with patch.object(client, "_access_token", return_value="token"), \
                    patch.object(client, "_request_json", return_value={"errorCode": 1}):
                client.read_ap_port_vlans(site_ref, ap_ref)


if __name__ == "__main__":
    unittest.main()
