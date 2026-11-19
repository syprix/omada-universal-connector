from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class ClientOutageOverlapIntegrationTests(unittest.TestCase):
    def test_selected_clients_use_same_window_and_documented_disconnect_codes(self):
        site_ref = "a" * 24
        client_a, client_b = "b" * 24, "c" * 24
        ap_ref = "d" * 24
        start_ms, end_ms = 1_789_372_800_000, 1_789_372_860_000
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site-internal"
        client._client_macs_by_site_ref[site_ref] = {
            client_a: "00-11-22-33-44-55", client_b: "00-11-22-33-44-66"}
        client._device_macs_by_site_ref[site_ref] = {ap_ref: "00-11-22-33-44-77"}

        calls = []

        def timeline(_site, ref, kind, start, end):
            calls.append((ref, kind, start, end))
            times = {client_a: (start_ms + 10_000, start_ms + 40_000),
                     client_b: (start_ms + 20_000, start_ms + 50_000)}[ref]
            event_type = 1 if kind == "disconnect" else 0
            event_time = times[0] if event_type == 1 else times[1]
            return {"status": "ok", "partial": False, "missing_fields": [],
                    "omitted_field_count": 0,
                    "data": {"sessions": [{"events": [{
                        "time_ms": event_time, "event_type": event_type,
                        "access_point_ref": ap_ref}]}]}}

        with patch.object(client, "list_clients", return_value={"items": [
                {"client_ref": client_a}, {"client_ref": client_b}]}), \
                patch.object(client, "list_devices", return_value={"items": [
                    {"device_ref": ap_ref}]}), \
                patch.object(client, "read_client_timeline", side_effect=timeline):
            result = client.read_site_client_outage_overlap_summary(
                site_ref, [client_a, client_b], start_ms, end_ms)

        self.assertEqual(calls, [
            (client_a, "connect", start_ms, end_ms),
            (client_a, "disconnect", start_ms, end_ms),
            (client_b, "connect", start_ms, end_ms),
            (client_b, "disconnect", start_ms, end_ms),
        ])
        self.assertEqual(result["confirmed_overlaps_by_access_point"], [{
            "access_point_ref": ap_ref,
            "confirmed_overlapping_client_pair_count": 1,
            "affected_client_count": 2,
        }])
        self.assertEqual(result["connection_cause"], "not_inferred")
        self.assertFalse(result["partial"])


if __name__ == "__main__":
    unittest.main()
