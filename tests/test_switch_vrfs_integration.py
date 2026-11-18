from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class SwitchVrfIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller_1", "client-id", "client-secret",
            tls_trust="system_ca", max_pages=4,
        ))
        self.client._site_ids_by_ref["a" * 24] = "site_1"
        self.client._switch_macs_by_site_ref["a" * 24] = {"b" * 24: "AA:BB:CC:DD:EE:FF"}

    def test_reads_unpaged_contract_and_returns_only_aggregates(self) -> None:
        rows = [{"id": "secret-id", "vrf": "secret-name", "ipv4Enable": True,
                 "ipv6Enable": True, "isDefault": True, "resource": 0}]
        with patch.object(self.client, "_access_token", return_value="fixture-token"), \
                patch.object(self.client, "_request_json", return_value={"result": {
                    "data": rows, "totalRows": 1, "currentPage": 0, "currentSize": 1}}) as read:
            result = self.client.list_switch_vrfs("a" * 24, "b" * 24)
        read.assert_called_once_with(
            "GET", "/openapi/v1/controller_1/sites/site_1/switches/AA:BB:CC:DD:EE:FF/vrfs",
            token="fixture-token",
        )
        self.assertEqual(result["resource"], "switch_vrfs")
        self.assertEqual(result["summary"]["default_count"], 1)
        self.assertNotIn("secret-name", repr(result))
        self.assertNotIn("secret-id", repr(result))

    def test_retries_with_documented_pagination_after_http_rejection(self) -> None:
        rows = [{"ipv4Enable": True, "ipv6Enable": False,
                 "isDefault": False, "resource": 1}]
        with patch.object(self.client, "_access_token", return_value="fixture-token"), \
                patch.object(self.client, "_request_json",
                             side_effect=OpenApiError("openapi_rejected", 400)) as request, \
                patch.object(self.client, "_read_pages", return_value=rows) as read:
            result = self.client.list_switch_vrfs("a" * 24, "b" * 24)
        request.assert_called_once_with(
            "GET", "/openapi/v1/controller_1/sites/site_1/switches/AA:BB:CC:DD:EE:FF/vrfs",
            token="fixture-token",
        )
        self.assertEqual(read.call_args.args[0],
                         "/openapi/v1/controller_1/sites/site_1/switches/AA:BB:CC:DD:EE:FF/vrfs")
        self.assertEqual(result["count"], 1)

    def test_rejects_unknown_switch_reference_before_request(self) -> None:
        with self.assertRaises(OpenApiError) as error:
            self.client.list_switch_vrfs("a" * 24, "c" * 24)
        self.assertEqual(error.exception.code, "switch_ref_unknown")


if __name__ == "__main__":
    unittest.main()
