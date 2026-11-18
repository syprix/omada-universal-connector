from __future__ import annotations

import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError

from app.site_switch_health_history import (
    SiteSwitchHealthHistoryError, project_site_switch_health_history,
)


START = 1_700_000_000_000
END = START + 86_400_000
REFS = [f"{i:024x}" for i in range(1, 4)]


class SiteSwitchHealthHistoryTests(unittest.TestCase):
    def test_maps_documented_timeline_to_opaque_refs_and_marks_missing_switch(self) -> None:
        mac1, mac2 = "001122334455", "aabbccddeeff"
        result = project_site_switch_health_history(
            {"timeline": [{"mac": "00:11:22:33:44:55", "scores": [
                {"time": START, "score": 81}, {"time": END, "score": 77}]}]},
            {mac1: [REFS[0]], mac2: [REFS[1]]}, REFS[:2], START, END)
        self.assertEqual(result["data"][0]["switch_ref"], REFS[0])
        self.assertEqual(result["data"][0]["scores"], [
            {"time_ms": START, "score": 81}, {"time_ms": END, "score": 77}])
        self.assertEqual(result["missing_switch_refs"], [REFS[1]])
        self.assertTrue(result["partial"])
        self.assertNotIn("00:11:22:33:44:55", repr(result))

    def test_unknown_mac_and_ambiguous_inventory_are_omitted(self) -> None:
        result = project_site_switch_health_history(
            {"timeline": [
                {"mac": "00:11:22:33:44:55", "scores": []},
                {"mac": "aa:bb:cc:dd:ee:ff", "scores": []},
            ]},
            {"001122334455": [REFS[0], REFS[1]]}, REFS[:2], START, END)
        self.assertEqual(result["data"], [])
        self.assertTrue(result["partial"])
        self.assertIn("ambiguous_inventory_mapping", result["omitted_fields"])
        self.assertIn("unmapped_or_duplicate_switch_rows", result["omitted_fields"])
        self.assertNotIn("aa:bb:cc:dd:ee:ff", repr(result))

    def test_device_cap_and_missing_source_field_are_explicit(self) -> None:
        result = project_site_switch_health_history(
            {}, {}, REFS, START, END, max_switches=2)
        self.assertEqual(result["devices_queried"], 2)
        self.assertEqual(result["unqueried_switch_refs"], [REFS[2]])
        self.assertTrue(result["partial"])
        with self.assertRaises(SiteSwitchHealthHistoryError):
            project_site_switch_health_history(
                {"timeline": []}, {}, REFS, START, END, max_switches=65)

    def test_client_uses_bounded_inventory_bound_batch_route(self) -> None:
        site_ref = "a" * 24
        mac = "00:11:22:33:44:55"
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site-1"
        seen: list[str] = []

        def read_pages(path, _token):
            self.assertTrue(path.endswith("/devices"))
            return [{"deviceId": "private-device-id", "deviceType": "switch", "mac": mac}]

        def request(method, path, *, token=None):
            self.assertEqual(method, "GET")
            self.assertEqual(token, "test-token")
            seen.append(path)
            parsed = urlsplit(path)
            query = parse_qs(parsed.query)
            self.assertEqual(parsed.path,
                             "/openapi/v1/ctrl/sites/site-1/switches/health/timeline")
            self.assertEqual(query["macs"], [mac])
            self.assertEqual(int(query["end"][0]) - int(query["start"][0]), 86_400_000)
            return {"result": {"timeline": [{"mac": mac, "scores": []}]}}

        with patch.object(client, "_access_token", return_value="test-token"), \
                patch.object(client, "_read_pages", side_effect=read_pages), \
                patch.object(client, "_request_json", side_effect=request):
            result = client.read_site_switch_health_history(site_ref)
        self.assertEqual(result["resource"], "site_switch_health_history")
        self.assertEqual(result["devices_queried"], 1)
        self.assertEqual(len(result["data"]), 1)
        self.assertEqual(result["data"][0]["scores"], [])
        self.assertTrue(result["data"][0]["switch_ref"].isalnum())
        for raw in (mac, "private-device-id", "site-1"):
            self.assertNotIn(raw, repr(result))
        self.assertEqual(len(seen), 1)

    def test_unknown_site_does_not_read_inventory_or_controller_timeline(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        with patch.object(client, "_read_pages") as read_pages:
            with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
                client.read_site_switch_health_history("a" * 24)
        read_pages.assert_not_called()

    def test_upstream_allowlist_requires_unique_bounded_macs_and_one_day_window(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        valid = ("/openapi/v1/ctrl/sites/site-1/switches/health/timeline?"
                 "macs=00-11-22-33-44-55%2CAA-BB-CC-DD-EE-FF&start=1700000000000&end=1700086400000")
        self.assertTrue(client._site_switch_health_history_request_valid(valid))
        self.assertFalse(client._site_switch_health_history_request_valid(
            valid.replace("end=1700086400000", "end=1700086399999")))
        self.assertFalse(client._site_switch_health_history_request_valid(
            valid.replace("macs=00-11-22-33-44-55%2CAA-BB-CC-DD-EE-FF",
                          "macs=00-11-22-33-44-55%2C00:11:22:33:44:55")))
        self.assertFalse(client._site_switch_health_history_request_valid(
            valid.replace("macs=00-11-22-33-44-55%2CAA-BB-CC-DD-EE-FF",
                          "macs=00-11-22-33-44-55&macs=AA-BB-CC-DD-EE-FF")))


if __name__ == "__main__":
    unittest.main()
