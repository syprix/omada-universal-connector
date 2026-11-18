from __future__ import annotations

import unittest
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


DAY_MS = 86_400_000


class FixedDateTime:
    @staticmethod
    def now(tz=None):
        return datetime(2026, 11, 16, 12, 0, tzinfo=tz or timezone.utc)


class MspHealthTimelineAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.msp_ref, self.customer_ref = "msp-1", "customer-2"
        self.site_ref = "a" * 24
        self.ap_ref, self.gateway_ref, self.switch_ref = "b" * 24, "c" * 24, "d" * 24
        self.site_id = "site_1"
        self.ap_mac, self.gateway_mac, self.switch_mac = (
            "00-11-22-33-44-55", "00-11-22-33-44-66", "00-11-22-33-44-77")
        self.client._site_ids_by_ref[self.site_ref] = self.site_id
        self.client._device_macs_by_site_ref[self.site_ref] = {self.ap_ref: self.ap_mac}
        self.client._gateway_macs_by_site_ref[self.site_ref] = {self.gateway_ref: self.gateway_mac}
        self.client._switch_macs_by_site_ref[self.site_ref] = {self.switch_ref: self.switch_mac}

    def test_three_msp_health_reads_use_fixed_daily_paths_and_redacted_projectors(self) -> None:
        expected = (
            (self.client.read_msp_ap_health_timeline, self.ap_ref,
             f"/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/eaps/{self.ap_mac}/health/timeline",
             "msp_ap_health_timeline", "device_ref"),
            (self.client.read_msp_gateway_health_timeline, self.gateway_ref,
             f"/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/gateways/{self.gateway_mac}/health/timeline",
             "msp_gateway_health_timeline", "gateway_ref"),
            (self.client.read_msp_switch_health_timeline, self.switch_ref,
             f"/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/switches/{self.switch_mac}/health/timeline",
             "msp_switch_health_timeline", "switch_ref"),
        )
        end_ms = int(FixedDateTime.now(timezone.utc).timestamp() * 1000)
        start_ms = end_ms - DAY_MS
        for method, ref, expected_path, resource, _ref_field in expected:
            calls = []
            def request(verb, path, **_kwargs):
                calls.append((verb, path))
                return {"result": {"scores": [{"time": end_ms, "score": 91,
                                                   "privateLabel": "private-value"}]}}
            with self.subTest(resource=resource), patch("app.openapi.datetime", FixedDateTime), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", side_effect=request):
                result = method(self.msp_ref, self.customer_ref, self.site_ref, ref)
            self.assertEqual(result["resource"], resource)
            self.assertNotIn("private-value", str(result))
            self.assertEqual(result["window_start_ms"], start_ms)
            self.assertEqual(result["window_end_ms"], end_ms)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], "GET")
            parsed = urlsplit(calls[0][1])
            self.assertEqual(parsed.path, expected_path)
            query = parse_qs(parsed.query, strict_parsing=True)
            self.assertEqual(set(query), {"start", "end"})
            self.assertEqual((int(query["start"][0]), int(query["end"][0])),
                             (start_ms, end_ms))

    def test_three_msp_health_details_use_fixed_daily_paths_and_bounded_projectors(self) -> None:
        expected = (
            (self.client.read_msp_ap_health_detail, self.ap_ref,
             f"/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/eaps/{self.ap_mac}/health/detail",
             "msp_ap_health_detail"),
            (self.client.read_msp_gateway_health_detail, self.gateway_ref,
             f"/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/gateways/{self.gateway_mac}/health/detail",
             "msp_gateway_health_detail"),
            (self.client.read_msp_switch_health_detail, self.switch_ref,
             f"/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/switches/{self.switch_mac}/health/detail",
             "msp_switch_health_detail"),
        )
        end_ms = int(FixedDateTime.now(timezone.utc).timestamp() * 1000)
        start_ms = end_ms - DAY_MS
        for method, ref, expected_path, resource in expected:
            calls = []
            def request(verb, path, **_kwargs):
                calls.append((verb, path))
                return {"result": {"score": 87, "privateLabel": "private-value"}}
            with self.subTest(resource=resource), patch("app.openapi.datetime", FixedDateTime), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", side_effect=request):
                result = method(self.msp_ref, self.customer_ref, self.site_ref, ref)
            self.assertEqual(result["resource"], resource)
            self.assertNotIn("private-value", str(result))
            self.assertEqual((result["window_start_ms"], result["window_end_ms"]), (start_ms, end_ms))
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], "GET")
            parsed = urlsplit(calls[0][1])
            self.assertEqual(parsed.path, expected_path)
            query = parse_qs(parsed.query, strict_parsing=True)
            self.assertEqual(set(query), {"start", "end"})
            self.assertEqual((int(query["start"][0]), int(query["end"][0])), (start_ms, end_ms))

    def test_msp_health_detail_path_validator_requires_known_shape_and_24_hour_window(self) -> None:
        good = (f"/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/gateways/{self.gateway_mac}"
                f"/health/detail?start=1000&end={1000 + DAY_MS}")
        self.assertTrue(self.client._msp_health_detail_request_valid(good))
        self.assertFalse(self.client._msp_health_detail_request_valid(good.replace("health/detail", "health/timeline")))
        self.assertFalse(self.client._msp_health_detail_request_valid(good.replace("msp-1", "../msp")))

    def test_msp_health_path_validator_requires_known_shape_and_24_hour_window(self) -> None:
        good = (f"/openapi/v1/msp/msp-1/customers/customer-2/sites/site_1/switches/{self.switch_mac}"
                f"/health/timeline?start=1000&end={1000 + DAY_MS}")
        self.assertTrue(self.client._msp_health_timeline_request_valid(good))
        for path in (good.replace("msp-1", "../msp"),
                     good.replace("switches", "other"),
                     good.replace(str(1000 + DAY_MS), str(1001 + DAY_MS)),
                     good + "&extra=1"):
            with self.subTest(path=path):
                self.assertFalse(self.client._msp_health_timeline_request_valid(path))

    def test_msp_and_customer_references_are_validated_before_request(self) -> None:
        for invalid_msp, invalid_customer in (("../msp", "customer-2"),
                                               ("msp-1", "customer/2"),
                                               (7, "customer-2"),
                                               ("msp-1", None)):
            with self.subTest(msp=invalid_msp, customer=invalid_customer), \
                    patch.object(self.client, "_request_json") as request, \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    self.assertRaises(OpenApiError):
                self.client.read_msp_switch_health_timeline(
                    invalid_msp, invalid_customer, self.site_ref, self.switch_ref)
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
