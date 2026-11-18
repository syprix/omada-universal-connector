from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
from app.site_log_window_summary import summarize_site_log_window


class SiteIdentityAndLogWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=2, max_pages=2))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-internal"

    def test_identity_resolver_requires_unique_wireless_name_and_ssid(self):
        rows = [
            {"name": "Sample client", "ssid": "Lab WLAN", "wireless": True,
             "mac": "AA:BB:CC:DD:EE:01", "rssi": -52},
            {"name": "Sample client", "ssid": "Guest WLAN", "wireless": True,
             "mac": "AA:BB:CC:DD:EE:02"},
            {"name": "Sample client", "ssid": "Lab WLAN", "wireless": False,
             "mac": "AA:BB:CC:DD:EE:03"},
        ]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows):
            result = self.client.resolve_site_client_identity(
                self.site_ref, "sample client", "lab wlan")
        self.assertEqual(result["match_state"], "matched")
        self.assertEqual(result["match_count"], 1)
        self.assertTrue(result["search_coverage"]["complete"])
        self.assertEqual(result["search_coverage"]["fields"]["ssid"]["present_count"], 3)
        self.assertRegex(result["client_ref"], r"^[0-9a-f]{24}$")
        self.assertNotIn("Pixel", str(result))
        self.assertNotIn("AA:BB", str(result))
        self.assertEqual(self.client.current_client_diagnostic_inventory(
            self.site_ref)["clients"]["count"], 1)

    def test_identity_resolver_never_selects_ambiguous_match(self):
        old_ref = "b" * 24
        self.client._client_macs_by_site_ref[self.site_ref] = {old_ref: "AA:BB:CC:DD:EE:FF"}
        self.client._client_items_by_site_ref[self.site_ref] = [{"client_ref": old_ref}]
        rows = [{"hostName": "Sample client", "ssid": "Lab WLAN", "wireless": True,
                 "mac": "AA:BB:CC:DD:EE:01"},
                {"model": "Sample client", "ssid": "Lab WLAN", "wireless": True,
                 "mac": "AA:BB:CC:DD:EE:02"}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows):
            result = self.client.resolve_site_client_identity(
                self.site_ref, "Sample client", "Lab WLAN")
        self.assertEqual(result["match_state"], "ambiguous")
        self.assertIsNone(result["client_ref"])
        self.assertFalse(result["partial"])
        self.assertEqual(result["search_coverage"]["potential_match_count"], 0)
        self.assertEqual(self.client._client_macs_by_site_ref[self.site_ref], {})
        self.assertEqual(self.client.current_client_diagnostic_inventory(
            self.site_ref)["clients"]["count"], 0)
        with self.assertRaises(OpenApiError):
            self.client.resolve_site_client_identity(self.site_ref, " Pixel", "Home")

    def test_missing_name_ssid_or_wireless_field_is_an_incomplete_search(self):
        rows_by_missing_field = {
            "name": [{"ssid": "Lab WLAN", "wireless": True}],
            "ssid": [{"name": "Sample client", "wireless": True}],
            "wireless": [{"name": "Sample client", "ssid": "Lab WLAN"}],
        }
        for missing_field, rows in rows_by_missing_field.items():
            with self.subTest(missing_field=missing_field), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_read_pages", return_value=rows):
                result = self.client.resolve_site_client_identity(
                    self.site_ref, "Sample client", "Lab WLAN")
            self.assertEqual(result["match_state"], "incomplete")
            self.assertEqual(result["match_count"], 0)
            self.assertIsNone(result["client_ref"])
            self.assertTrue(result["partial"])
            self.assertFalse(result["search_coverage"]["complete"])
            self.assertEqual(result["search_coverage"]["fields"][missing_field]["missing_count"], 1)

    def test_complete_nonmatch_is_a_confident_unmatched_result(self):
        rows = [{"name": "Other client", "hostName": "Other client", "model": "Other model",
                 "ssid": "Lab WLAN", "wireless": True},
                {"name": "Sample client", "ssid": "Guest WLAN", "wireless": True},
                {"name": "Sample client", "ssid": "Lab WLAN", "wireless": False}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows):
            result = self.client.resolve_site_client_identity(
                self.site_ref, "Sample client", "Lab WLAN")
        self.assertEqual(result["match_state"], "unmatched")
        self.assertEqual(result["match_count"], 0)
        self.assertIsNone(result["client_ref"])
        self.assertFalse(result["partial"])
        self.assertTrue(result["search_coverage"]["complete"])

    def test_one_match_with_an_incomplete_possible_duplicate_is_not_selected(self):
        rows = [{"name": "Sample client", "ssid": "Lab WLAN", "wireless": True,
                 "mac": "AA:BB:CC:DD:EE:01"},
                {"ssid": "Lab WLAN", "wireless": True}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_pages", return_value=rows):
            result = self.client.resolve_site_client_identity(
                self.site_ref, "Sample client", "Lab WLAN")
        self.assertEqual(result["match_state"], "incomplete")
        self.assertEqual(result["match_count"], 1)
        self.assertIsNone(result["client_ref"])
        self.assertEqual(result["search_coverage"]["potential_match_count"], 1)

    def test_event_summary_pages_past_controller_statistics(self):
        first = {"result": {"data": [{"id": "private1", "time": 1_700_000_000_000,
                                      "module": "system"}], "totalRows": 3,
                            "currentPage": 1, "currentSize": 2,
                            "eventLogStat": {"totalLogNum": 3, "systemLogNum": 1,
                                             "deviceLogNum": 1, "clientLogNum": 1}}}
        second = {"result": {"data": [{"id": "private2", "time": 1_700_000_000_001,
                                       "module": "device"},
                                      {"id": "private3", "time": 1_700_000_000_002,
                                       "module": "client"}], "totalRows": 3,
                             "currentPage": 2, "currentSize": 2}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[first, second]) as request:
            result = self.client.read_site_log_window_summary(
                self.site_ref, "events", 1_700_000_000_000, 1_700_000_000_100)
        self.assertEqual(request.call_count, 2)
        self.assertFalse(result["partial"])
        self.assertEqual(result["returned_count"], 3)
        self.assertEqual(result["controller_module_totals"],
                         {"client": 1, "device": 1, "system": 1})
        self.assertNotIn("private1", str(result))

    def test_paging_limit_is_reported_as_partial(self):
        def response(page):
            rows = [{"id": f"private-{page}-{idx}", "time": 1_700_000_000_000 + idx,
                     "module": "system", "level": "warning"} for idx in (1, 2)]
            return {"result": {"data": rows, "totalRows": 6, "currentPage": page,
                               "currentSize": 2}}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=[response(1), response(2)]):
            result = self.client.read_site_log_window_summary(
                self.site_ref, "alerts", 1_700_000_000_000, 1_700_000_000_100)
        self.assertTrue(result["partial"])
        self.assertEqual(result["total_count"], 6)
        self.assertEqual(result["returned_count"], 4)

    def test_summary_rejects_out_of_window_rows(self):
        with self.assertRaises(ValueError):
            summarize_site_log_window([{"time": 12, "module": "system"}],
                                      "events", 10, 11, 1)

    def test_all_three_source_contract_reviews_are_recorded(self):
        path = Path(__file__).resolve().parents[1] / "docs/CONTRACT_MATRIX.json"
        matrix = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["sources"]), 3)
        expected = {
            "site_client_identity_match": "getGridActiveClients",
            "site_events_window_summary": "getEventLogsForSite",
            "site_alerts_window_summary": "getAlertLogsForSite",
        }
        for source in matrix["sources"]:
            for operation_id, source_id in expected.items():
                row = source["operations"][operation_id]
                self.assertTrue(row["documented"])
                self.assertEqual(row["live_support"], "unknown")
                self.assertEqual(row["contract_review"]["operation_id"], source_id)


if __name__ == "__main__":
    unittest.main()
