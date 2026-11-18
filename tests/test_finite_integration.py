from __future__ import annotations

import unittest
from unittest.mock import patch

from app.omada import OmadaConfig, OmadaError
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE = "a" * 24
GATEWAY = "b" * 24
SWITCH = "c" * 24


def openapi_config(timeout=5.0) -> OpenApiConfig:
    return OpenApiConfig("https://controller.example", "ctrl", "client-id", "client-secret",
                         cert_sha256="a" * 64, timeout_seconds=timeout)


class FiniteIntegrationTests(unittest.TestCase):
    def test_timeout_configs_reject_bad_types_and_huge_integers_stably(self) -> None:
        invalid = (True, False, "5", None, 10**400)
        for value in invalid:
            with self.subTest(config="openapi", value=type(value).__name__), \
                    self.assertRaisesRegex(OpenApiError, "timeout_invalid"):
                openapi_config(value)
            with self.subTest(config="omada", value=type(value).__name__), \
                    self.assertRaisesRegex(OmadaError, "controller_timeout_invalid"):
                OmadaConfig("https://controller.example", timeout_seconds=value)

        self.assertEqual(openapi_config(5.0).timeout_seconds, 5.0)
        self.assertEqual(OmadaConfig("https://controller.example", timeout_seconds=5.0).timeout_seconds, 5.0)

    def test_large_integer_gateway_wan_loss_is_invalid_response(self) -> None:
        client = OmadaOpenApiClient(openapi_config())
        client._site_ids_by_ref[SITE] = "site_known"
        client._gateway_macs_by_site_ref[SITE] = {GATEWAY: "AA-BB-CC-DD-EE-FF"}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": [{"loss": 10**400}]}), \
                self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
            client.read_gateway_wan_status(SITE, GATEWAY)

    def test_large_integer_switch_poe_power_is_invalid_response(self) -> None:
        client = OmadaOpenApiClient(openapi_config())
        client._site_ids_by_ref[SITE] = "site_known"
        client._switch_macs_by_site_ref[SITE] = {SWITCH: "AA-BB-CC-DD-EE-FF"}
        row = {"switchMac": "AA-BB-CC-DD-EE-FF", "port": 1,
               "portStatus": {"poePower": 10**400}}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_read_pages", return_value=[row]), \
                self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
            client.read_switch_ports(SITE, SWITCH)

    def test_large_integer_site_power_consumption_is_invalid_response(self) -> None:
        client = OmadaOpenApiClient(openapi_config())
        client._site_ids_by_ref[SITE] = "site_known"
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={
                    "result": {"powerConsumption": 10**400}}), \
                self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
            client.read_site_overview(SITE)


if __name__ == "__main__":
    unittest.main()
