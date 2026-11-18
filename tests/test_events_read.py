from __future__ import annotations

import re
import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class SiteEventReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site_1"

    def test_events_return_opaque_refs_time_and_safe_module_only(self) -> None:
        now = 1_800_000_000_000
        payload = {"result": {"totalRows": 1, "currentPage": 1, "currentSize": 1,
                              "data": [{"id": "event-1", "module": "Device", "time": now,
                                        "content": "Secret router 192.0.2.1", "key": "private"}]}}
        paths = []
        def request(method, path, **kwargs):
            paths.append(path)
            self.assertEqual(method, "GET")
            self.assertTrue(OmadaOpenApiClient._SITE_LOG_REQUEST.fullmatch(path))
            return payload
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            with patch("app.openapi.datetime") as dt:
                dt.now.return_value.timestamp.return_value = now / 1000
                dt.now.return_value = __import__("datetime").datetime.fromtimestamp(now / 1000,
                                                               __import__("datetime").timezone.utc)
                result = self.client.list_site_events(self.site_ref)
        self.assertEqual(result["items"][0]["module"], "device")
        self.assertEqual(result["items"][0]["time_ms"], now)
        self.assertNotIn("event-1", str(result))
        self.assertNotIn("192.0.2.1", str(result))
        self.assertNotIn("private", str(result))
        self.assertEqual(len(paths), 1)
        capability = next(item for item in self.client.capabilities()["items"]
                          if item["operation"] == "site_events")
        self.assertEqual(capability["runtime_evidence"][0]["result"], "success")

    def test_alerts_normalize_severity_and_drop_free_text(self) -> None:
        now = 1_800_000_000_000
        rows = [{"id": "alert-secret-id", "module": "Unrecognized private module", "time": now,
                 "level": "WARNING", "content": "Name private 10.0.0.1"}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_site_log_pages",
                             return_value=(rows, len(rows), None)), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = __import__("datetime").datetime.fromtimestamp(now / 1000,
                                                               __import__("datetime").timezone.utc)
            result = self.client.list_site_alerts(self.site_ref)
        item = result["items"][0]
        self.assertEqual(item["severity"], "warning")
        self.assertEqual(item["module"], "other")
        for forbidden in ("alert-secret-id", "private", "10.0.0.1"):
            self.assertNotIn(forbidden, str(result))

    def test_rejects_out_of_window_time_and_unknown_site(self) -> None:
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            self.client.list_site_events("b" * 24)
        now = 1_800_000_000_000
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_site_log_pages", return_value=([
                    {"id": "e1", "module": "System", "time": now + 40 * 24 * 60 * 60 * 1000}],
                    1, None)), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = __import__("datetime").datetime.fromtimestamp(now / 1000,
                                                               __import__("datetime").timezone.utc)
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.list_site_events(self.site_ref)

    def test_event_summary_does_not_stop_paginated_event_reads(self) -> None:
        now = 1_800_000_000_000
        rows = [{"id": f"event-{index}", "module": "Device", "time": now}
                for index in range(100)]
        calls = []

        def request(method, path, **kwargs):
            calls.append(path)
            page = int(re.search(r"[?&]page=(\d+)", path).group(1))
            page_rows = rows if page == 1 else [
                {"id": f"event-{(page - 1) * 100 + index}", "module": "Device", "time": now}
                for index in range(100)
            ] if page == 2 else [
                {"id": f"event-{(page - 1) * 100 + index}", "module": "Device", "time": now}
                for index in range(50)
            ]
            result = {"totalRows": 250, "currentPage": page,
                      "currentSize": len(page_rows), "data": page_rows}
            if page == 1:
                result["eventLogStat"] = {"totalLogNum": 250, "systemLogNum": 10,
                                          "deviceLogNum": 230, "clientLogNum": 10}
            return {"result": result}

        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = __import__("datetime").datetime.fromtimestamp(
                now / 1000, __import__("datetime").timezone.utc)
            result = self.client.list_site_events(self.site_ref)

        self.assertEqual(len(calls), 3)
        self.assertEqual([int(re.search(r"[?&]page=(\d+)", path).group(1)) for path in calls],
                         [1, 2, 3])
        self.assertEqual(result["count"], 250)
        self.assertEqual(result["total_count"], 250)
        self.assertFalse(result["partial"])
        self.assertEqual(result["module_counts"],
                         {"system": 10, "device": 230, "client": 10})

    def test_event_summary_rejects_inconsistent_totals(self) -> None:
        now = 1_800_000_000_000
        payload = {"result": {
            "totalRows": 3, "currentPage": 1, "currentSize": 1,
            "data": [{"id": "event-1", "module": "System", "time": now}],
            "eventLogStat": {"totalLogNum": 3, "systemLogNum": 1,
                             "deviceLogNum": 1, "clientLogNum": 0},
        }}
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value=payload), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = __import__("datetime").datetime.fromtimestamp(
                now / 1000, __import__("datetime").timezone.utc)
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.list_site_events(self.site_ref)

    def test_events_without_summary_keep_page_limit_error(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=1, max_pages=1))
        client._site_ids_by_ref[self.site_ref] = "site_1"
        now = 1_800_000_000_000
        payload = {"result": {
            "totalRows": 2, "currentPage": 1, "currentSize": 1,
            "data": [{"id": "event-1", "module": "System", "time": now}],
        }}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=payload), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = __import__("datetime").datetime.fromtimestamp(
                now / 1000, __import__("datetime").timezone.utc)
            with self.assertRaisesRegex(OpenApiError, "openapi_page_limit_reached"):
                client.list_site_events(self.site_ref)

    def test_fixed_time_bounded_read_allowlist(self) -> None:
        path = "/openapi/v1/ctrl/sites/site_1/logs/alerts?page=1&pageSize=100&filters.timeStart=10&filters.timeEnd=20"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", path)
        for invalid in (path + "&searchKey=secret", path.replace("filters.timeStart=10", "filters.timeStart=10.2")):
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", invalid)
        with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
            self.client._request_json("DELETE", path)


if __name__ == "__main__":
    unittest.main()
