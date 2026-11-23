from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_static_route_interface_options_summary import (
    StaticRouteInterfaceOptionsError,
    summarize_static_route_interface_options,
)


class StaticRouteInterfaceOptionsTests(unittest.TestCase):
    def test_counts_documented_interface_types_and_next_hop_values(self):
        result = summarize_static_route_interface_options({
            "hasWanEnable": True,
            "interfaceInfoList": [
                {"id": "private-id", "name": "private-name",
                 "interfaceType": 0, "needNextHop": True},
                {"id": "private-id-2", "name": "private-name-2",
                 "interfaceType": 1, "needNextHop": False},
                {"interfaceType": 2, "needNextHop": True},
                {"interfaceType": 3},
                {"interfaceType": 5, "needNextHop": False},
                {"interfaceType": 9, "needNextHop": True},
            ],
        })
        self.assertEqual(result["scope"], "static_route_selection_options")
        self.assertEqual(result["reported_interface_option_count"], 6)
        self.assertEqual(result["interface_type_counts"], {
            "wan": 1, "lan": 1, "l2tp": 1, "pptp": 1,
            "virtual_wan": 1, "unknown": 1,
        })
        self.assertEqual(result["need_next_hop_value_counts"], {
            "true": 3, "false": 2, "unknown": 1,
        })
        self.assertTrue(result["has_wan_enabled"])
        self.assertTrue(result["partial"])
        for private in ("private-id", "private-name"):
            self.assertNotIn(private, repr(result))
        self.assertNotIn("interfaceType", repr(result))

    def test_marks_missing_and_invalid_fields_and_truncation(self):
        result = summarize_static_route_interface_options({
            "interfaceInfoList": [
                {"interfaceType": True, "needNextHop": "yes", "extra": "private"},
                {"interfaceType": 0, "needNextHop": False},
                {"interfaceType": 1, "needNextHop": True},
            ],
        }, max_items=2)
        self.assertEqual(result["returned_interface_option_count"], 2)
        self.assertEqual(result["reported_interface_option_count"], 3)
        self.assertTrue(result["truncated"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_field_count"], 2)
        self.assertEqual(result["unknown_field_count"], 1)
        with self.assertRaises(StaticRouteInterfaceOptionsError):
            summarize_static_route_interface_options({"interfaceInfoList": {}})

    def test_client_uses_the_selected_site_and_fixed_read_path(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        site_ref = "a" * 24
        client._site_ids_by_ref[site_ref] = "selected_site"
        path = ("/openapi/v1/ctrl/sites/selected_site/"
                "routing/static-routings/interfaces")
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": {
                    "interfaceInfoList": [{"interfaceType": 0, "needNextHop": True}],
                    "hasWanEnable": True,
                }}) as request:
            result = client.read_site_static_route_interface_options_summary(site_ref)
        request.assert_called_once_with("GET", path, token="token")
        self.assertEqual(result["site_ref"], site_ref)
        self.assertEqual(result["interface_type_counts"]["wan"], 1)
        self.assertTrue(result["has_wan_enabled"])
        self.assertTrue(client._site_static_route_interface_options_request_valid(path))
        self.assertFalse(client._site_static_route_interface_options_request_valid(
            "/openapi/v1/other/sites/selected_site/routing/static-routings/interfaces"))

    def test_unknown_site_is_rejected_before_upstream_read(self):
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        with patch.object(client, "_access_token") as access, \
                patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_static_route_interface_options_summary("a" * 24)
        access.assert_not_called()
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
