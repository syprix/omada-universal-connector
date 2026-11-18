from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ClientDetailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref, self.other_site_ref = "a" * 24, "c" * 24
        self.client._site_ids_by_ref = {self.site_ref: "site_1", self.other_site_ref: "site_2"}

    def _list_clients(self, site_ref: str, mac="00:11:22:33:44:55"):
        self.client._read_pages = lambda *_args: [{"mac": mac, "wireless": True, "active": True}]
        with patch.object(self.client, "_access_token", return_value="token"):
            return self.client.list_clients(site_ref)["items"][0]["client_ref"]

    def test_maps_client_ref_to_fixed_detail_request_and_redacts_identity(self) -> None:
        ref = self._list_clients(self.site_ref)
        raw = {"id": "private-id", "mac": "00:11:22:33:44:55", "name": "private name",
               "hostName": "private host", "ip": "192.0.2.1", "ssid": "Private WiFi",
               "apName": "Private AP", "apMac": "00:11:22:33:44:66", "rssi": -57,
               "snr": 32, "signalLevel": 87, "signalRank": 4, "radioId": 1,
               "channel": 44, "rxRate": 866, "txRate": 720, "wireless": True,
               "active": True, "blocked": False, "guest": False, "connectDevType": "AP",
               "activity": 1200, "uploadActivity": 300, "trafficDown": 9000,
               "trafficUp": 4000, "uptime": 120, "lastSeen": 1800000000000,
               "healthScore": 98, "description": "private", "authStatus": 2}
        calls = []
        def request(method, path, **kwargs):
            calls.append((method, path))
            return {"result": raw}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = self.client.read_client_detail(self.site_ref, ref)
        self.assertEqual(calls[0], ("GET", "/openapi/v1/ctrl/sites/site_1/clients/00:11:22:33:44:55"))
        self.assertEqual(result["client_ref"], ref)
        self.assertEqual(result["rssi"], -57)
        self.assertEqual(result["signal_level"], 87)
        self.assertEqual(result["connection_device_type"], "ap")
        self.assertEqual(result["active"], True)
        for forbidden in ("private-id", "private name", "private host", "192.0.2.1",
                          "Private WiFi", "Private AP", "00:11:22:33:44:55", "healthScore"):
            self.assertNotIn(forbidden, str(result))
        evidence = next(x for x in self.client.capabilities()["items"]
                        if x["operation"] == "client_detail")["runtime_evidence"]
        self.assertEqual(evidence[0]["target_ref"], self.site_ref + ":" + ref)

    def test_refresh_invalidates_prior_ref_and_site_isolation(self) -> None:
        ref1 = self._list_clients(self.site_ref)
        snapshot1 = self.client.current_client_diagnostic_inventory(self.site_ref)
        ref2 = self._list_clients(self.other_site_ref)
        self.assertNotEqual(ref1, ref2)
        ref3 = self._list_clients(self.site_ref)
        self.assertNotEqual(ref1, ref3)
        snapshot3 = self.client.current_client_diagnostic_inventory(self.site_ref)
        self.assertEqual(snapshot1["clients"]["items"][0]["client_ref"], ref1)
        self.assertEqual(snapshot3["clients"]["items"][0]["client_ref"], ref3)
        with self.assertRaisesRegex(OpenApiError, "client_ref_unknown"):
            self.client.read_client_detail(self.site_ref, ref1)
        with self.assertRaisesRegex(OpenApiError, "client_ref_unknown"):
            self.client.read_client_detail(self.site_ref, ref2)

    def test_site_inventory_refresh_clears_client_refs(self) -> None:
        ref = self._list_clients(self.site_ref)
        self.assertEqual(
            self.client.current_client_diagnostic_inventory(self.site_ref)["clients"]["items"][0]["client_ref"],
            ref,
        )
        self.client._read_pages = lambda *_args: [{"siteId": "site_1"}]
        with patch.object(self.client, "_access_token", return_value="token"):
            self.client.list_sites()
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.current_client_diagnostic_inventory(self.site_ref)
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.read_client_detail(self.site_ref, ref)

    def test_invalid_detail_schema_and_fixed_path_are_rejected(self) -> None:
        ref = self._list_clients(self.site_ref)
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {"signalLevel": 101}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_client_detail(self.site_ref, ref)
        path = "/openapi/v1/ctrl/sites/site_1/clients/00-11-22-33-44-55"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", path)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", "/openapi/v1/ctrl/sites/site_1/clients/not-a-mac")
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("DELETE", path)


if __name__ == "__main__":
    unittest.main()
