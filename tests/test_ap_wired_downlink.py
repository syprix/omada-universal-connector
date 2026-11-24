from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_wired_downlink import ApWiredDownlinkError, project_ap_wired_downlink
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_REF, AP_REF, PEER_REF = "a" * 24, "b" * 24, "c" * 24
AP_MAC, PEER_MAC = "00:11:22:33:44:55", "00-11-22-33-44-66"


def _row(mac: str = PEER_MAC) -> dict[str, object]:
    return {"port": "eth1", "portType": 1, "duplex": 1, "link": 1,
            "speed": 1000, "poeState": 1, "voipState": 0, "mac": mac,
            "ip": "192.0.2.4", "type": "Switch", "deviceName": "private-name",
            "model": "SW-8", "modelVersion": "1.0", "txPower": 1.5,
            "rxPower": 2.5, "temp": 38.5, "voltage": 48.0, "current": 0.3,
            "rxPkts": 10, "txPkts": 20, "rx": 1000, "tx": 2000,
            "rxDropPkts": 1, "txDropPkts": 2, "rxErrPkts": 3, "txErrPkts": 4,
            "downLinkPort": "1/0/1", "display": True}


class ApWiredDownlinkProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.refs = {"001122334466": PEER_REF}

    def test_maps_known_device_mac_and_redacts_addresses_names_and_models(self) -> None:
        result = project_ap_wired_downlink({"wiredDownlinkList": [_row()]}, self.refs)
        self.assertFalse(result["partial"])
        row = result["items"][0]
        self.assertEqual(row["device_ref"], PEER_REF)
        self.assertEqual(row["speed"], 1000)
        for private in (PEER_MAC, "192.0.2.4", "private-name", "SW-8", "1.0"):
            self.assertNotIn(private, repr(result))

    def test_unknown_or_ambiguous_mac_is_not_returned_and_marks_partial(self) -> None:
        result = project_ap_wired_downlink({"wiredDownlinkList": [_row("02:00:00:00:00:01")]}, {})
        self.assertTrue(result["partial"])
        self.assertNotIn("device_ref", result["items"][0])
        self.assertNotIn("02:00:00:00:00:01", repr(result))
        ambiguous = project_ap_wired_downlink({"wiredDownlinkList": [_row()]},
                                              {"001122334466": None})
        self.assertTrue(ambiguous["partial"])

    def test_empty_list_is_valid_and_malformed_or_unbounded_shapes_fail_closed(self) -> None:
        empty = project_ap_wired_downlink({"wiredDownlinkList": []}, self.refs)
        self.assertEqual(empty["count"], 0)
        self.assertFalse(empty["partial"])
        self.assertTrue(empty["collection_reported"])
        missing = project_ap_wired_downlink({}, self.refs)
        self.assertEqual(missing["count"], 0)
        self.assertIsNone(missing["source_count"])
        self.assertFalse(missing["collection_reported"])
        self.assertEqual(missing["missing_collection_count"], 1)
        self.assertTrue(missing["partial"])
        for raw in (None, [], {"wiredDownlinkList": None},
                    {"wiredDownlinkList": [{}] * 257}):
            with self.subTest(raw=raw), self.assertRaises(ApWiredDownlinkError):
                project_ap_wired_downlink(raw, self.refs)
        invalid = _row()
        invalid["speed"] = True
        invalid["display"] = 1
        result = project_ap_wired_downlink({"wiredDownlinkList": [invalid]}, self.refs)
        self.assertTrue(result["partial"])
        self.assertNotIn("speed", result["items"][0])
        self.assertNotIn("display", result["items"][0])


class ApWiredDownlinkClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"
        self.client._device_macs_by_site_ref[SITE_REF] = {AP_REF: AP_MAC}
        self.client._inventory_macs_by_site_ref[SITE_REF] = {
            AP_REF: AP_MAC, PEER_REF: PEER_MAC,
        }

    def test_reads_exact_route_and_projects_mapped_opaque_ref(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={
                    "result": {"wiredDownlinkList": [_row()]}}) as request:
            result = self.client.read_ap_wired_downlink(SITE_REF, AP_REF)
        request.assert_called_once_with(
            "GET", f"/openapi/v1/ctrl/sites/site_1/aps/{AP_MAC}/wired-downlink",
            token="token")
        self.assertEqual(result["resource"], "ap_wired_downlink")
        self.assertEqual(result["items"][0]["device_ref"], PEER_REF)
        self.assertNotIn(AP_MAC, repr(result))
        self.assertNotIn(PEER_MAC, repr(result))

    def test_fixed_path_allowlist_and_inventory_binding(self) -> None:
        path = f"/openapi/v1/ctrl/sites/site_1/aps/{AP_MAC}/wired-downlink"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", path)
        with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
            self.client.read_ap_wired_downlink(SITE_REF, "d" * 24)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("GET", path + "?include=private")


if __name__ == "__main__":
    unittest.main()
