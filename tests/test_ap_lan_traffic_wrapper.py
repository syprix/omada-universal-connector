from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_REF = "a" * 24
DEVICE_REF = "b" * 24
AP_MAC = "AA:BB:CC:DD:EE:FF"
PRIVATE_VALUE = "private-wrapper-value"


class ApLanTrafficWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "controller", "unused-id", "unused-secret",
            cert_sha256="a" * 64,
        ))
        self.client._site_ids_by_ref = {SITE_REF: "private-site-id"}
        self.client._device_macs_by_site_ref = {SITE_REF: {DEVICE_REF: AP_MAC}}

    def call(self, result: object) -> dict[str, object]:
        with patch.object(self.client, "_access_token", return_value="synthetic-token"), \
             patch.object(self.client, "_request_json", return_value={"result": result}):
            return self.client.read_ap_lan_traffic(SITE_REF, DEVICE_REF)

    def test_unknown_result_sibling_marks_partial_without_echoing_key_or_value(self) -> None:
        values = {"rxPkts": 1, "txPkts": 2, "rx": 3, "tx": 4,
                  "rxDropPkts": 5, "txDropPkts": 6, "rxErrPkts": 7, "txErrPkts": 8}
        result = self.call({"lanTraffic": values, "privateSibling": PRIVATE_VALUE})
        self.assertTrue(result["partial"])
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertEqual(result["data"], values)
        self.assertNotIn("privateSibling", repr(result))
        self.assertNotIn(PRIVATE_VALUE, repr(result))
        self.assertNotIn("private-site-id", repr(result))
        self.assertNotIn(AP_MAC, repr(result))

    def test_result_wrapper_type_field_count_and_key_bounds_fail_closed(self) -> None:
        malformed = (None, [], {f"x{i}": None for i in range(33)}, {"x" * 129: None})
        for result in malformed:
            with self.subTest(kind=type(result).__name__), self.assertRaises(OpenApiError) as caught:
                self.call(result)
            self.assertEqual(caught.exception.code, "openapi_response_invalid")


if __name__ == "__main__":
    unittest.main()
