import unittest
from unittest.mock import patch

from app.ap_channel_load_summary import summarize_ap_channel_load_result
from app.openapi import OpenApiConfig, OmadaOpenApiClient


class ApChannelLoadSummaryTests(unittest.TestCase):
    def test_aggregates_loads_by_band_and_suppresses_channel_values(self):
        result = summarize_ap_channel_load_result({
            "channelLoads2g": [{"channel": 1, "load": 20}, {"channel": 6, "load": 80}],
            "channelLoads5g": [{"channel": 36, "load": 42}],
            "channelLoads6g": []})
        self.assertEqual(result["data"]["bands"]["2g"], {
            "returned_channel_count": 2, "minimum_load": 20, "maximum_load": 80,
            "average_load": 50.0})
        self.assertEqual(result["data"]["bands"]["5g"]["average_load"], 42.0)
        self.assertFalse(result["partial"])
        self.assertNotIn('"channel"', repr(result))

    def test_client_uses_fixed_site_ap_get_and_redacts_identity(self):
        client = OmadaOpenApiClient(OpenApiConfig("https://controller.example", "ctrl", "id", "secret",
                                                   cert_sha256="a" * 64))
        site_ref, ap_ref = "a" * 24, "b" * 24
        client._site_ids_by_ref[site_ref] = "site_1"
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "AA-BB-CC-DD-EE-FF"}
        result_body = {"channelLoads2g": [{"channel": 1, "load": 20}],
                       "channelLoads5g": [], "channelLoads6g": []}
        with patch.object(client, "_access_token", return_value="token"), patch.object(
                client, "_request_json", return_value={"result": result_body}) as request:
            result = client.read_ap_channel_load_summary(site_ref, ap_ref)
        request.assert_called_once_with("GET", "/openapi/v1/ctrl/sites/site_1/aps/AA-BB-CC-DD-EE-FF/full-channel-detect/channel-load", token="token")
        self.assertEqual(result["resource"], "ap_channel_load_summary")
        self.assertNotIn("AA-BB-CC-DD-EE-FF", repr(result))

    def test_wrong_result_shape_is_rejected(self):
        with self.assertRaises(ValueError):
            summarize_ap_channel_load_result([])


if __name__ == "__main__":
    unittest.main()
