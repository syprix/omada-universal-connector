from __future__ import annotations

import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class ClientRoamingBacktrackIntegrationTests(unittest.TestCase):
    def test_selected_client_reads_roaming_connect_disconnect_and_joins_bound_ap_refs(self):
        site_ref, client_ref = "a" * 24, "b" * 24
        ap_a, ap_b = "c" * 24, "d" * 24
        start_ms, end_ms = 1_789_372_800_000, 1_789_372_860_000
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64))
        client._site_ids_by_ref[site_ref] = "site-internal"
        client._client_macs_by_site_ref[site_ref] = {
            client_ref: "00-11-22-33-44-55"}
        client._device_macs_by_site_ref[site_ref] = {
            ap_a: "00-11-22-33-44-66", ap_b: "00-11-22-33-44-77"}
        calls = []

        def timeline(_site, selected_client, kind, start, end):
            calls.append((selected_client, kind, start, end))
            event_type = {"connect": 0, "disconnect": 1, "roaming": 2}[kind]
            events = ([
                {"time_ms": start_ms + 1_000, "event_type": 2,
                 "previous_access_point_ref": ap_a, "access_point_ref": ap_b},
                {"time_ms": start_ms + 2_000, "event_type": 2,
                 "previous_access_point_ref": ap_b, "access_point_ref": ap_a},
            ] if kind == "roaming" else [])
            return {"status": "ok", "partial": False, "missing_fields": [],
                    "omitted_fields": [], "omitted_field_count": 0,
                    "data": {"sessions": [{"events": events}]}}

        with patch.object(client, "list_clients", return_value={"items": [
                {"client_ref": client_ref}]}), \
                patch.object(client, "list_devices", return_value={"items": []}), \
                patch.object(client, "read_client_timeline", side_effect=timeline):
            result = client.read_site_client_roaming_backtrack_summary(
                site_ref, [client_ref], start_ms, end_ms)

        self.assertEqual(calls, [(client_ref, kind, start_ms, end_ms)
                                 for kind in ("roaming", "disconnect", "connect")])
        self.assertEqual(result["back_and_forth_by_access_point_pair"], [{
            "access_point_pair": [ap_a, ap_b],
            "back_and_forth_sequence_count": 1,
            "affected_client_count": 1,
            "involved_roaming_event_count": 2,
        }])
        self.assertEqual(result["connection_cause"], "not_inferred")
        self.assertFalse(result["partial"])


if __name__ == "__main__":
    unittest.main()
