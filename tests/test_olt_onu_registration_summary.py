from __future__ import annotations

import unittest
from unittest.mock import patch

from app.olt_onu_registration_summary import (
    OltOnuRegistrationError, project_olt_onu_auto_auth_status,
    project_olt_onu_autofind_summary,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class OltOnuRegistrationProjectionTests(unittest.TestCase):
    def test_auto_authentication_is_a_boolean_and_unknown_fields_are_omitted(self) -> None:
        result = project_olt_onu_auto_auth_status({
            "autoAuthenticationStatus": "DISABLE", "unknown": "private"})
        self.assertEqual(result["data"], {"auto_authentication_enabled": False})
        self.assertTrue(result["partial"])
        self.assertNotIn("private", repr(result))

    def test_autofind_omits_raw_pon_scope_and_bounds_interval(self) -> None:
        result = project_olt_onu_autofind_summary({
            "ponPort": "GPON 1/1/1,GPON 1/1/3-5", "agingTimeStatus": "TIMEOUT",
            "agingTime": 3, "autofindInterval": 5,
        })
        self.assertEqual(result["data"], {
            "pon_port_scope_configured": True, "aging_time_status": "TIMEOUT",
            "aging_time_code": 3, "autofind_interval_seconds": 5,
        })
        self.assertFalse(result["partial"])
        self.assertNotIn("GPON 1/1/1", repr(result))

    def test_invalid_status_interval_and_large_payload_are_rejected_or_partial(self) -> None:
        result = project_olt_onu_autofind_summary({
            "ponPort": "x", "agingTimeStatus": "BAD", "autofindInterval": 20})
        self.assertTrue(result["partial"])
        self.assertEqual(result["invalid_count"], 2)
        with self.assertRaises(OltOnuRegistrationError):
            project_olt_onu_auto_auth_status({f"unknown{n}": n for n in range(5)})
        with self.assertRaises(OltOnuRegistrationError):
            project_olt_onu_autofind_summary([])


class OltOnuRegistrationAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.device_ref = "a" * 24, "b" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"
        self.client._inventory_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00-11-22-33-44-55"}
        self.client._olt_macs_by_site_ref[self.site_ref] = {
            self.device_ref: "00:11:22:33:44:55"}

    def test_fixed_inventory_bound_gets(self) -> None:
        cases = (
            ("read_olt_onu_auto_auth_status",
             "pon/onu-register/auto-authentication/global/configs/get",
             {"autoAuthenticationStatus": "ENABLE"}),
            ("read_olt_onu_autofind_summary", "pon/onu-register/autofind/configs/get",
             {"agingTimeStatus": "NO_AGING", "autofindInterval": 2}),
        )
        for method, suffix, payload in cases:
            with self.subTest(method=method), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": payload}) as request:
                result = getattr(self.client, method)(self.site_ref, self.device_ref)
                self.assertEqual(result["site_ref"], self.site_ref)
                self.assertEqual(result["device_ref"], self.device_ref)
                self.assertEqual(request.call_args.args[0], "GET")
                self.assertTrue(request.call_args.args[1].endswith(suffix))

    def test_allowlist_and_inventory_binding(self) -> None:
        path = ("/openapi/v1/ctrl/sites/site_1/olts/00-11-22-33-44-55/"
                "pon/onu-register/autofind/configs/get")
        self.assertTrue(self.client._olt_onu_autofind_request_valid(path))
        self.assertFalse(self.client._olt_onu_autofind_request_valid(path.replace("ctrl", "other")))
        self.client._olt_macs_by_site_ref[self.site_ref] = {}
        with patch.object(self.client, "_request_json") as request, \
                self.assertRaisesRegex(OpenApiError, "device_type_unsupported"):
            self.client.read_olt_onu_autofind_summary(self.site_ref, self.device_ref)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
