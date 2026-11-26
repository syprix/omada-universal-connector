import unittest
from unittest.mock import patch

from app.operation_registry import REGISTRY, RegistryError
from app.openapi import OpenApiConfig, OpenApiError, OmadaOpenApiClient
from app.site_voucher_currency_options import (
    MAX_CURRENCY_CODE_LENGTH,
    SiteVoucherCurrencyOptionsError,
    project_site_voucher_currency_options,
)


class SiteVoucherCurrencyOptionsTests(unittest.TestCase):
    def client(self):
        return OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))

    def test_normal_and_empty_lists_preserve_selected_string(self):
        normal = project_site_voucher_currency_options({
            "currencyList": ["EUR", "USD"], "selectedCurrency": "SITE-CODE"})
        self.assertEqual(normal["data"]["currency_codes"], ["EUR", "USD"])
        self.assertEqual(normal["data"]["selected_currency_code"], "SITE-CODE")
        self.assertFalse(normal["partial"])
        # The selected field is independent; no membership or ISO inference is made.
        empty = project_site_voucher_currency_options({
            "currencyList": [], "selectedCurrency": ""})
        self.assertEqual(empty["data"]["currency_codes"], [])
        self.assertEqual(empty["data"]["selected_currency_code"], "")
        self.assertTrue(empty["data"]["currency_list_present"])
        self.assertFalse(empty["partial"])

    def test_missing_fields_differ_from_valid_empty_list(self):
        missing_list = project_site_voucher_currency_options({"selectedCurrency": "X"})
        self.assertFalse(missing_list["data"]["currency_list_present"])
        self.assertEqual(missing_list["data"]["currency_codes"], [])
        self.assertEqual(missing_list["data"]["missing_field_count"], 1)
        self.assertTrue(missing_list["partial"])
        missing_selected = project_site_voucher_currency_options({"currencyList": []})
        self.assertTrue(missing_selected["data"]["currency_list_present"])
        self.assertFalse(missing_selected["data"]["selected_currency_field_present"])
        self.assertIsNone(missing_selected["data"]["selected_currency_code"])
        self.assertEqual(missing_selected["data"]["missing_field_count"], 1)
        self.assertTrue(missing_selected["partial"])

    def test_invalid_duplicates_extra_fields_and_bounded_values_are_partial(self):
        result = project_site_voucher_currency_options({
            "currencyList": ["A", "A", "", "x" * (MAX_CURRENCY_CODE_LENGTH + 1),
                             "bad\ncode", 3],
            "selectedCurrency": "selected-but-not-in-list",
            "extra": "private-value",
        })
        self.assertEqual(result["data"]["currency_codes"], [])
        self.assertEqual(result["data"]["currency_list_row_count"], 6)
        self.assertEqual(result["data"]["invalid_value_count"], 4)
        self.assertEqual(result["data"]["duplicate_currency_code_count"], 1)
        self.assertEqual(result["data"]["selected_currency_code"],
                         "selected-but-not-in-list")
        self.assertEqual(result["data"]["unknown_field_count"], 1)
        self.assertTrue(result["partial"])
        self.assertNotIn("private-value", repr(result))
        self.assertNotIn("extra", repr(result))

    def test_malformed_and_oversized_response_fails_closed(self):
        for result in (None, [], {"currencyList": "USD", "selectedCurrency": "USD"},
                       {"currencyList": ["C" + str(i) for i in range(101)],
                        "selectedCurrency": "USD"}):
            with self.subTest(shape=type(result).__name__):
                with self.assertRaises(SiteVoucherCurrencyOptionsError):
                    project_site_voucher_currency_options(result)

    def test_fixed_site_get_and_numeric_controller_failure(self):
        client = self.client()
        site_ref = "a" * 24
        client._site_ids_by_ref = {site_ref: "site-safe"}
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value={"errorCode": 0,
                    "result": {"currencyList": ["X1"], "selectedCurrency": "Y2",
                               "extra": "redact"}}) as request:
            result = client.read_site_voucher_currency_options(site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site-safe/hotspot/voucher-groups/currency-list",
            token="test-token")
        self.assertEqual(result["data"]["currency_codes"], ["X1"])
        self.assertEqual(result["data"]["selected_currency_code"], "Y2")
        self.assertTrue(result["partial"])
        self.assertNotIn("redact", repr(result))
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", return_value={"errorCode": -33000,
                                                                      "result": {}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                client.read_site_voucher_currency_options(site_ref)
        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_request_json", side_effect=OpenApiError("transport_error")):
            with self.assertRaisesRegex(OpenApiError, "transport_error"):
                client.read_site_voucher_currency_options(site_ref)

    def test_invalid_site_and_route_guard(self):
        client = self.client()
        with patch.object(client, "_request_json") as request:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_voucher_currency_options("a" * 24)
            request.assert_not_called()
        good = "/openapi/v1/ctrl/sites/site-safe/hotspot/voucher-groups/currency-list"
        self.assertTrue(client._site_voucher_currency_options_request_valid(good))
        for path in (good.replace("/ctrl/", "/other/"), good + "?x=1", good + "/extra"):
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                client._request_json("GET", path)

    def test_registry_maps_exact_read_route(self):
        op = REGISTRY.get("site_voucher_currency_options")
        self.assertEqual(op.public_template,
                         "/v1/sites/{site_ref}/hotspot/voucher-currency-options")
        self.assertEqual(op.upstream_template,
                         "/openapi/v1/{controller_id}/sites/{site_id}/hotspot/voucher-groups/currency-list")
        path = f"/v1/sites/{'a' * 24}/hotspot/voucher-currency-options"
        route, bindings = REGISTRY.match("GET", path)
        self.assertEqual(route.operation_id, "site_voucher_currency_options")
        self.assertEqual(dict(bindings), {"site_ref": "a" * 24})
        for method, shadow in (("POST", path), ("GET", path + "-shadow")):
            with self.assertRaises(RegistryError):
                REGISTRY.match(method, shadow)

    def test_capability_is_registered_without_live_support_claim(self):
        item = next(row for row in self.client().capabilities()["items"]
                    if row["operation"] == "site_voucher_currency_options")
        self.assertEqual(item["implementation_state"], "implemented")
        self.assertEqual(item["support_state"], "unknown")
        self.assertEqual(item["runtime_evidence_count"], 0)


if __name__ == "__main__":
    unittest.main()
