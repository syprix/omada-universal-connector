from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class SiteWifiSummaryIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_reads_exact_documented_route_with_fixed_24_hour_seconds_window(self) -> None:
        with patch("app.openapi.datetime") as clock:
            clock.now.return_value.timestamp.return_value = 1_800_000_000.75
            with patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={
                        "result": {"connectedApNum": 4, "clients": 23,
                                   "channelUtilization": 38, "totalTraffic": 678.5}}) as request:
                result = self.client.read_site_wifi_summary(self.site_ref)
        request.assert_called_once()
        method, path = request.call_args.args[:2]
        self.assertEqual(method, "GET")
        parsed = urlsplit(path)
        self.assertEqual(parsed.path,
                         "/openapi/v1/ctrl/sites/site_1/dashboard/wifi-summary")
        query = parse_qs(parsed.query, strict_parsing=True)
        self.assertEqual(set(query), {"start", "end"})
        self.assertEqual(int(query["end"][0]) - int(query["start"][0]), 86_400)
        self.assertEqual(result["window_end_seconds"], int(query["end"][0]))
        self.assertEqual(result["data"]["clients"], 23)

    def test_rejects_other_controller_extra_query_and_wrong_window(self) -> None:
        good = "/openapi/v1/ctrl/sites/site_1/dashboard/wifi-summary?start=100000&end=186400"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
        for bad in (
                good.replace("/ctrl/", "/other/"),
                good + "&extra=1",
                good.replace("end=186400", "end=186401"),
                good.replace("start=100000", "start=0")):
            with self.subTest(path=bad), self.assertRaisesRegex(
                    OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", bad)
    def test_reads_6ghz_ap_presence_from_the_exact_documented_site_route(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"exist6GAp": True}}) as request:
            result = self.client.read_site_6ghz_ap_presence(self.site_ref)
        request.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/site_1/wireless-network/multi-band-6g/exist",
            token="token")
        self.assertEqual(result["resource"], "site_6ghz_ap_presence")
        self.assertIs(result["data"]["has_6ghz_ap"], True)

    def test_rejects_invalid_6ghz_response_and_unrelated_controller_path(self) -> None:
        for value in (None, {}, {"exist6GAp": 1}, {"exist6GAp": "true"}):
            with self.subTest(value=value), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": value}), \
                    self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_site_6ghz_ap_presence(self.site_ref)
        good = "/openapi/v1/ctrl/sites/site_1/wireless-network/multi-band-6g/exist"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", good)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", good.replace("/ctrl/", "/other/"))


if __name__ == "__main__":
    unittest.main()
