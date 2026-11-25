from __future__ import annotations

import re
import time
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
        query = dict(part.split("=", 1) for part in paths[0].split("?", 1)[1].split("&"))
        self.assertEqual(int(query["filters.timeEnd"]), now)
        self.assertEqual(int(query["filters.timeStart"]), now - 30 * 24 * 60 * 60 * 1000)
        self.assertEqual(result["items"][0]["module"], "device")
        self.assertEqual(result["items"][0]["time_ms"], now)
        self.assertNotIn("event-1", str(result))
        self.assertNotIn("192.0.2.1", str(result))
        self.assertNotIn("private", str(result))
        self.assertEqual(len(paths), 1)
        capability = next(item for item in self.client.capabilities()["items"]
                          if item["operation"] == "site_events")
        self.assertEqual(capability["runtime_evidence"][0]["result"], "success")

    def test_events_accept_a_short_explicit_window(self) -> None:
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - 5 * 60 * 1000
        payload = {"result": {"totalRows": 1, "currentPage": 1, "currentSize": 1,
                              "data": [{"id": "event-1", "module": "System",
                                        "time": end_ms}]}}
        paths = []

        def request(method, path, **kwargs):
            paths.append(path)
            return payload

        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request):
            result = self.client.list_site_events(self.site_ref, start_ms, end_ms)

        self.assertEqual(len(paths), 1)
        self.assertIn(f"filters.timeStart={start_ms}", paths[0])
        self.assertIn(f"filters.timeEnd={end_ms}", paths[0])
        self.assertEqual(result["window_start_ms"], start_ms)
        self.assertEqual(result["window_end_ms"], end_ms)
        self.assertFalse(result["partial"])

    def test_pagewise_events_read_one_page_per_call_for_6056_rows(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=200))
        client._site_ids_by_ref[self.site_ref] = "site_1"
        now = int(time.time() * 1000)
        start_ms, end_ms = now - 30 * 86_400_000, now
        calls: list[str] = []

        def request(method, path, **kwargs):
            self.assertEqual(method, "GET")
            calls.append(path)
            query = dict(part.split("=", 1) for part in path.split("?", 1)[1].split("&"))
            page = int(query["page"])
            size = int(query["pageSize"])
            rows = [{"id": f"event-{index}", "module": "Device",
                     "time": end_ms, "content": "private event text"}
                    for index in range((page - 1) * size, min(page * size, 6056))]
            return {"result": {"totalRows": 6056, "currentPage": page,
                               "currentSize": len(rows), "data": rows}}

        observed_refs: set[str] = set()
        total_rows = 0
        expected_total = None
        for page in range(1, 32):
            before = len(calls)
            with patch.object(client, "_access_token", return_value="token"), \
                    patch.object(client, "_request_json", side_effect=request):
                result = client.list_site_events(
                    self.site_ref, start_ms, end_ms, page_number=page,
                    page_size=200, expected_total=expected_total)
            self.assertEqual(len(calls) - before, 1)
            expected_total = result["total_count"]
            refs = [item["event_ref"] for item in result["items"]]
            self.assertEqual(len(refs), len(set(refs)))
            self.assertFalse(observed_refs.intersection(refs))
            observed_refs.update(refs)
            total_rows += result["count"]
            self.assertEqual(result["window_start_ms"], start_ms)
            self.assertEqual(result["window_end_ms"], end_ms)
            self.assertEqual(result["pagination"]["page_number"], page)
            self.assertEqual(result["pagination"]["next_page"], page + 1 if page < 31 else None)
            self.assertEqual(result["partial"], result["count"] < result["total_count"])
            self.assertEqual(result["pagination"]["window_exhausted"], page == 31)
            self.assertNotIn("private event text", str(result))

        self.assertEqual(total_rows, 6056)
        self.assertEqual(len(observed_refs), 6056)
        self.assertEqual(len(calls), 31)

    def test_pagewise_events_fails_for_changed_total_or_wrong_page(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=200))
        client._site_ids_by_ref[self.site_ref] = "site_1"
        now = int(time.time() * 1000)
        start_ms, end_ms = now - 30 * 86_400_000, now
        payload = {"result": {"totalRows": 201, "currentPage": 2,
                              "currentSize": 1,
                              "data": [{"id": "event-200", "module": "System",
                                        "time": end_ms}]}}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=payload):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                client.list_site_events(
                    self.site_ref, start_ms, end_ms, page_number=2,
                    page_size=200, expected_total=202)
        payload["result"]["totalRows"] = 201
        payload["result"]["currentPage"] = 1
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=payload):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                client.list_site_events(
                    self.site_ref, start_ms, end_ms, page_number=2,
                    page_size=200, expected_total=201)
        payload["result"]["totalRows"] = 202
        payload["result"]["currentPage"] = 2
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=payload):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                client.list_site_events(
                    self.site_ref, start_ms, end_ms, page_number=2,
                    page_size=200, expected_total=202)

    def test_pagewise_event_uses_fixed_allowlisted_request_once(self) -> None:
        import json

        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=200))
        client._site_ids_by_ref[self.site_ref] = "site_1"
        now = int(time.time() * 1000)
        start_ms, end_ms = now - 30 * 86_400_000, now
        response_body = json.dumps({"result": {
            "totalRows": 6056, "currentPage": 31, "currentSize": 56,
            "data": [{"id": f"event-{i}", "module": "Device", "time": end_ms}
                     for i in range(6000, 6056)]}}, separators=(",", ":")).encode()

        class Response:
            status = 200
            def getheader(self, name, default=""):
                return "application/json" if name == "Content-Type" else default
            def read(self, limit=-1):
                return response_body[:limit]

        class Connection:
            _omada_tls_verified = True
            def __init__(self):
                self.requests = []
            def request(self, method, path, **kwargs):
                self.requests.append((method, path, kwargs))
            def getresponse(self):
                return Response()
            def close(self):
                pass

        connection = Connection()
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_connection", return_value=connection):
            result = client.list_site_events(
                self.site_ref, start_ms, end_ms, page_number=31,
                page_size=200, expected_total=6056)

        self.assertEqual(len(connection.requests), 1)
        method, path, _headers = connection.requests[0]
        self.assertEqual(method, "GET")
        self.assertEqual(path, (
            "/openapi/v1/ctrl/sites/site_1/logs/events?page=31&pageSize=200&"
            f"filters.timeStart={start_ms}&filters.timeEnd={end_ms}"))
        self.assertEqual(result["count"], 56)
        self.assertEqual(result["total_count"], 6056)

    def test_pagewise_events_rejects_duplicate_refs_and_page_budget_overflow(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=200))
        client._site_ids_by_ref[self.site_ref] = "site_1"
        now = int(time.time() * 1000)
        start_ms, end_ms = now - 30 * 86_400_000, now
        duplicate = {"result": {"totalRows": 2, "currentPage": 1,
                                "currentSize": 2,
                                "data": [{"id": "same", "module": "System", "time": end_ms},
                                         {"id": "same", "module": "System", "time": end_ms}]}}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=duplicate):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                client.list_site_events(
                    self.site_ref, start_ms, end_ms, page_number=1, page_size=200)

        page64 = {"result": {"totalRows": 12_801, "currentPage": 64,
                             "currentSize": 200,
                             "data": [{"id": f"event-{i}", "module": "System",
                                       "time": end_ms} for i in range(12_600, 12_800)]}}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=page64):
            result = client.list_site_events(
                self.site_ref, start_ms, end_ms, page_number=64,
                page_size=200, expected_total=12_801)
        self.assertTrue(result["partial"])
        self.assertTrue(result["pagination"]["page_limit_reached"])
        self.assertIsNone(result["pagination"]["next_page"])

    def test_pagewise_events_validate_30_day_window_and_continuation_before_request(self) -> None:
        now = int(time.time() * 1000)
        cases = (
            (now - 30 * 86_400_000 - 1, now, 1, 200, None),
            (now - 1_000, now + 120_000, 1, 200, None),
            (now - 60_000, now, 65, 200, None),
            (now - 60_000, now, 2, 200, None),
            (now - 60_000, now, 1, 200, 1),
            (now - 60_000, now, 2, 200, 0),
            (now, now, 1, 100, None),
            (now - 60_000, now, 1, 101, None),
            (now - 60_000, now, 1, 201, None),
        )
        with patch.object(self.client, "_request_json") as request:
            for start_ms, end_ms, page, size, expected_total in cases:
                with self.subTest(page=page, size=size, expected_total=expected_total):
                    with patch.object(self.client, "_access_token", return_value="token"):
                        with self.assertRaises(OpenApiError):
                            self.client.list_site_events(
                                self.site_ref, start_ms, end_ms,
                                page_number=page, page_size=size,
                                expected_total=expected_total)
            request.assert_not_called()

    def test_events_reject_invalid_explicit_windows_before_request(self) -> None:
        end_ms = int(time.time() * 1000)
        invalid_windows = (
            (end_ms - 1_000, None),
            (end_ms, end_ms - 1_000),
            (end_ms - 24 * 60 * 60 * 1000 - 1, end_ms),
            (end_ms - 1_000, end_ms + 120_000),
        )
        with patch.object(self.client, "_read_site_log_pages") as read_pages:
            for start_ms, window_end_ms in invalid_windows:
                with self.subTest(start_ms=start_ms, end_ms=window_end_ms):
                    with self.assertRaisesRegex(OpenApiError, "time_window_invalid"):
                        self.client.list_site_events(self.site_ref, start_ms, window_end_ms)
        read_pages.assert_not_called()

    def test_events_page_limit_still_fails_closed_with_explicit_window(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret",
            cert_sha256="a" * 64, page_size=1, max_pages=1))
        client._site_ids_by_ref[self.site_ref] = "site_1"
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - 5 * 60 * 1000
        payload = {"result": {"totalRows": 2, "currentPage": 1, "currentSize": 1,
                              "data": [{"id": "event-1", "module": "System",
                                        "time": end_ms}]}}
        with patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value=payload):
            with self.assertRaisesRegex(OpenApiError, "openapi_page_limit_reached"):
                client.list_site_events(self.site_ref, start_ms, end_ms)

    def test_alerts_normalize_severity_and_drop_free_text(self) -> None:
        now = 1_800_000_000_000
        rows = [{"id": "alert-secret-id", "module": "Unrecognized private module", "time": now,
                 "level": "WARNING", "content": "Name private 10.0.0.1"}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_read_site_log_pages",
                             return_value=(rows, len(rows), None, 1)), \
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
                    1, None, 1)), \
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

    def test_controller_window_summary_uses_bounded_global_read_and_redacts_rows(self) -> None:
        now = int(time.time() * 1000)
        calls = []
        payload = {"result": {"totalRows": 1, "currentPage": 1, "currentSize": 1,
                              "data": [{"id": "private-event", "module": "System",
                                        "content": "SSID private-name", "time": now}]}}
        def request(method, path, **kwargs):
            calls.append(path)
            self.assertEqual(method, "GET")
            self.assertRegex(path, r"^/openapi/v1/ctrl/logs/events\?page=1&pageSize=100&filters\.timeStart=[0-9]+&filters\.timeEnd=[0-9]+$")
            return payload
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", side_effect=request), \
                patch("app.openapi.datetime") as dt:
            dt.now.return_value = __import__("datetime").datetime.fromtimestamp(
                now / 1000, __import__("datetime").timezone.utc)
            result = self.client.read_controller_log_window_summary("events", now - 60_000, now)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["scope"], "configured_controller")
        self.assertEqual(result["returned_count"], 1)
        self.assertEqual(result["resource"], "controller_events_window_summary")
        for forbidden in ("private-event", "private-name", "site_id", "site_ref"):
            self.assertNotIn(forbidden, str(result))

    def test_controller_global_path_allowlist_is_controller_bound(self) -> None:
        path = "/openapi/v1/ctrl/logs/alerts?page=1&pageSize=100&filters.timeStart=10&filters.timeEnd=20"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", path)
        for invalid in (path.replace("/ctrl/", "/other/"), path + "&filters.resolved=false"):
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", invalid)


if __name__ == "__main__":
    unittest.main()
