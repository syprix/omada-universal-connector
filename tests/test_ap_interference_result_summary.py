import unittest
from unittest.mock import patch

from app.ap_interference_result_summary import summarize_ap_interference_result
from app.openapi import OpenApiConfig, OmadaOpenApiClient, OpenApiError


class ApInterferenceResultSummaryTests(unittest.TestCase):
    def test_counts_documented_recursive_bands_without_records(self):
        result = summarize_ap_interference_result({
            "interferences2g": [{"interferences2g": [], "interferences5g": [], "interferences6g": []}],
            "interferences5g": [], "interferences6g": [], "mac": "private"})
        self.assertEqual(result["data"]["band_entry_counts"], {"2g": 1, "5g": 0, "6g": 0})
        self.assertTrue(result["partial"])
        self.assertNotIn("private", repr(result))

    def test_client_binds_ap_and_fixed_first_page(self):
        client = OmadaOpenApiClient(OpenApiConfig("https://controller.example", "ctrl", "id", "secret",
                                                   cert_sha256="a" * 64))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site_1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA-BB-CC-DD-EE-FF"}
        response = {"result": {"interferences2g": [], "interferences5g": [], "interferences6g": []}}
        with patch.object(client, "_access_token", return_value="token"), patch.object(
                client, "_request_json", return_value=response) as request:
            result = client.read_ap_interference_result_summary(site_ref, ap_ref)
        request.assert_called_once_with("GET", "/openapi/v1/ctrl/sites/site_1/aps/AA-BB-CC-DD-EE-FF/full-channel-detect/grid/interference?page=1&pageSize=100", token="token")
        self.assertTrue(result["partial"])
        self.assertEqual(result["resource"], "ap_interference_result_summary")

    def test_wrong_result_shape_is_rejected(self):
        with self.assertRaises(ValueError):
            summarize_ap_interference_result([])


if __name__ == "__main__":
    unittest.main()
