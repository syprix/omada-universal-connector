from __future__ import annotations

import builtins
import io
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from app import main
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


TOKEN = "wifi-subhealth-integration-token-0123456789abcdef"
SITE_REF = "a" * 24
OTHER_SITE_REF = "b" * 24
PRIVATE_SITE_ID = "private-site-id"
PRIVATE_INCIDENT_ID = "private-incident-id"
PRIVATE_MAC = "AA-BB-CC-DD-EE-FF"
PRIVATE_TEXT = "client association failed private details"
PRIVATE_NAME = "private-office-ssid"
PRIVATE_IP = "192.0.2.91"
DAY_MS = 86_400_000


class FixedDateTime:
    @staticmethod
    def now(tz=None):
        return datetime(2026, 1, 2, 12, 0, tzinfo=tz or timezone.utc)


def full_result(start_ms: int, end_ms: int) -> dict[str, object]:
    simple = {
        "summaryScore": 81,
        "support": True,
        "scores": [{"time": start_ms, "score": 78}, {"time": end_ms, "score": 84}],
    }
    return {
        "wifiHealthScore": 82,
        "accessTimeScoreDetail": dict(simple),
        "channelUtilScoreDetail": dict(simple),
        "accessCapacityScoreDetail": dict(simple),
        "rssiScoreDetail": dict(simple),
        "channelInterUtilDetail": {
            **simple,
            "averageInterf2g": 14,
            "averageInterf5g": 21,
            "averageInterf6g": 9,
            "averageNoiseFloor": -92,
            "incidents": [{"id": PRIVATE_INCIDENT_ID, "mac": PRIVATE_MAC,
                           "message": PRIVATE_TEXT}],
        },
        "wirelessClientQualityDetail": {
            "summaryScore": 76,
            "support": True,
            "assocTime": [{"time": start_ms, "pastNum": 11}],
            "authTime": [{"time": start_ms, "pastNum": 12}],
            "dhcpTime": [{"time": end_ms, "pastNum": 13}],
            "dnsTime": [{"time": end_ms, "pastNum": 14}],
            "averageAssocTime": 100,
            "averageAuthTime": 200,
            "averageDhcpTime": 300,
            "averageDnsTime": 400,
            "incidents": [{"id": PRIVATE_INCIDENT_ID, "clientMac": PRIVATE_MAC,
                           "content": PRIVATE_TEXT}],
        },
    }


class WifiSubhealthIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp.name, "caller-token")
        with open(self.token_file, "w", encoding="ascii") as stream:
            stream.write(TOKEN)

        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = PRIVATE_SITE_ID
        now_ms = int(FixedDateTime.now(timezone.utc).timestamp() * 1000)
        self.start_ms, self.end_ms = now_ms - DAY_MS, now_ms
        self.upstream_result: object = full_result(self.start_ms, self.end_ms)
        self.upstream_calls: list[tuple[str, str, bytes | None]] = []
        self.fail_upstream = False

        def fake_request(method: str, path: str, body: bytes | None = None,
                         token: str | None = None):
            self.upstream_calls.append((method, path, body))
            self.assertEqual(method, "GET")
            self.assertIsNone(body)
            self.assertEqual(token, "synthetic-upstream-token")
            parsed = urlsplit(path)
            self.assertEqual(parsed.path,
                f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/wifi/sub/health/timeline")
            query = parse_qs(parsed.query, strict_parsing=True)
            self.assertEqual(set(query), {"start", "end"})
            start, end = int(query["start"][0]), int(query["end"][0])
            self.assertEqual(end - start, DAY_MS)
            self.assertEqual((start, end), (self.start_ms, self.end_ms))
            if self.fail_upstream:
                raise OpenApiError("openapi_rejected", -1001)
            return {"result": json.loads(json.dumps(self.upstream_result))}

        self.transport_patch = patch.object(self.client, "_request_json", side_effect=fake_request)
        self.transport_patch.start()
        self.access_patch = patch.object(
            self.client, "_access_token", return_value="synthetic-upstream-token")
        self.access_patch.start()
        self.clock_patch = patch("app.openapi.datetime", FixedDateTime)
        self.clock_patch.start()
        self.env_patch = patch.dict(os.environ, {"OMADA_CONNECTOR_TOKEN_FILE": self.token_file})
        self.env_patch.start()
        self.client_patch = patch.object(main, "_openapi_client", return_value=self.client)
        self.client_patch.start()
        self.logs = io.StringIO()
        self.print_patch = patch.object(
            builtins, "print", lambda *args, **_kwargs: self.logs.write(
                " ".join(map(str, args)) + "\n"))
        self.print_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.print_patch.stop()
        self.client_patch.stop()
        self.env_patch.stop()
        self.clock_patch.stop()
        self.access_patch.stop()
        self.transport_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def public_path(site_ref: str = SITE_REF) -> str:
        return f"/v1/sites/{site_ref}/wifi/health/details"

    def request(self, method: str, path: str, *, token: str | None = None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Authorization": "Bearer " + token} if token is not None else {}
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = {}
        status = response.status
        connection.close()
        return status, value

    def test_auth_site_binding_fixed_window_bands_and_onboarding(self) -> None:
        route = "GET /v1/sites/{site_ref}/wifi/health/details"
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == route)
        self.assertEqual(operation["support_state"], "unknown")
        self.assertEqual(operation["runtime_evidence"], [])

        status, denied = self.request("GET", self.public_path())
        self.assertEqual(status, 401)
        self.assertEqual(denied["error"], "unauthorized")
        self.assertEqual(self.upstream_calls, [])

        status, value = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertEqual(len(self.upstream_calls), 1)
        self.assertEqual(value["resource"], "wifi_subhealth")
        self.assertEqual(value["site_ref"], SITE_REF)
        self.assertEqual(value["window"], {"start_ms": self.start_ms, "end_ms": self.end_ms})
        self.assertEqual(self.upstream_calls[0][0], "GET")
        self.assertIsNone(self.upstream_calls[0][2])
        self.assertFalse(value["partial"])
        self.assertEqual(value["data"]["channelInterUtilDetail"]["averageInterf2g"], 14)
        self.assertEqual(value["data"]["channelInterUtilDetail"]["averageInterf5g"], 21)
        self.assertEqual(value["data"]["channelInterUtilDetail"]["averageInterf6g"], 9)
        self.assertEqual(value["data"]["wirelessClientQualityDetail"]["averageDhcpTime"], 300)
        self.assertEqual(value["data"]["wirelessClientQualityDetail"]["dhcpTime"],
                         [{"time_ms": self.end_ms, "pastNum": 13}])

        # ER7212PC omits wirelessClientQualityDetail in its export; report it as partial.
        self.upstream_result = full_result(self.start_ms, self.end_ms)
        self.upstream_result.pop("wirelessClientQualityDetail")
        status, er_value = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 200, er_value)
        self.assertTrue(er_value["partial"])
        self.assertIn("wirelessClientQualityDetail", er_value["missing_fields"])

        status, unknown = self.request("GET", self.public_path(OTHER_SITE_REF), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(unknown["error"], "site_ref_unknown")
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(unknown))

    def test_incident_ids_macs_and_freetext_are_fully_redacted(self) -> None:
        raw = full_result(self.start_ms, self.end_ms)
        raw["channelInterUtilDetail"]["incidents"] = [
            {"incidentId": PRIVATE_INCIDENT_ID, "clientMac": PRIVATE_MAC,
             "content": PRIVATE_TEXT, "ssid": PRIVATE_NAME, "ip": PRIVATE_IP}
        ]
        raw["wirelessClientQualityDetail"]["incidents"] = [
            {"id": PRIVATE_INCIDENT_ID, "mac": PRIVATE_MAC, "message": PRIVATE_TEXT}
        ]
        self.upstream_result = raw
        status, value = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        rendered = json.dumps(value)
        for private in (PRIVATE_INCIDENT_ID, PRIVATE_MAC, PRIVATE_TEXT,
                        PRIVATE_NAME, PRIVATE_IP, "incidentId", "clientMac", "content"):
            self.assertNotIn(private, rendered)
            self.assertNotIn(private, self.logs.getvalue())

    def test_missing_invalid_null_unknown_and_out_of_window_mark_partial(self) -> None:
        raw = full_result(self.start_ms, self.end_ms)
        raw["wifiHealthScore"] = None
        raw["accessTimeScoreDetail"]["support"] = "bad-private-support"
        raw["channelUtilScoreDetail"]["scores"] = [
            {"time": self.start_ms - 1, "score": 80},
            {"time": "private-invalid-time", "score": 81},
            {"time": self.end_ms, "score": True},
            {"time": self.end_ms, "score": 84, "extraPrivate": PRIVATE_TEXT},
        ]
        raw["rssiScoreDetail"].pop("summaryScore")
        raw["privateRoot"] = PRIVATE_TEXT
        self.upstream_result = raw
        status, value = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 200, value)
        self.assertTrue(value["partial"])
        rendered = json.dumps(value)
        for private in (PRIVATE_TEXT, "privateRoot", "extraPrivate", "private-invalid-time"):
            self.assertNotIn(private, rendered)
        self.assertIn("wifiHealthScore", value["invalid_fields"])
        self.assertIn("accessTimeScoreDetail.support", value["invalid_fields"])
        self.assertIn("rssiScoreDetail.summaryScore", value["missing_fields"])
        operation = next(item for item in self.client.capabilities()["items"]
                         if item["route"] == "GET /v1/sites/{site_ref}/wifi/health/details")
        self.assertEqual(operation["runtime_evidence"][-1]["support_state"], "unknown")
        self.assertEqual(operation["runtime_evidence"][-1]["observation"], "response_partial")

    def test_invalid_root_and_upstream_failure_are_redacted(self) -> None:
        self.upstream_result = None
        status, error = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_response_invalid")
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))

        self.fail_upstream = True
        status, error = self.request("GET", self.public_path(), token=TOKEN)
        self.assertEqual(status, 502)
        self.assertEqual(error["error"], "openapi_rejected")
        self.assertNotIn(PRIVATE_SITE_ID, json.dumps(error))

    def test_get_only_route_and_fixed_upstream_controller_and_window_allowlist(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "unused-id", "unused-secret",
            cert_sha256="a" * 64))
        good = (f"/openapi/v1/ctrl/sites/{PRIVATE_SITE_ID}/wifi/sub/health/timeline"
                f"?start={self.start_ms}&end={self.end_ms}")
        with patch.object(client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                client._request_json("GET", good, token="token")
            rejected = (
                ("POST", good), ("PUT", good), ("PATCH", good), ("DELETE", good),
                ("GET", good + "&debug=1"),
                ("GET", good.replace("/openapi/v1/ctrl/", "/openapi/v1/foreign/")),
                ("GET", good.replace("/wifi/sub/health/timeline", "/other")),
                ("GET", good.replace(f"start={self.start_ms}", f"start={self.start_ms - 1}")),
                ("GET", good.replace(f"end={self.end_ms}", f"end={self.end_ms + 1}")),
            )
            for method, path in rejected:
                with self.subTest(method=method, path=path), self.assertRaisesRegex(
                        OpenApiError, "openapi_path_rejected"):
                    client._request_json(method, path, token="token")

        for method in ("POST", "PUT", "PATCH", "DELETE"):
            status, _ = self.request(method, self.public_path(), token=TOKEN)
            self.assertNotEqual(status, 200)
        status, _ = self.request("GET", self.public_path() + "?debug=1", token=TOKEN)
        self.assertNotEqual(status, 200)
        self.assertEqual(self.upstream_calls, [])


if __name__ == "__main__":
    unittest.main()
