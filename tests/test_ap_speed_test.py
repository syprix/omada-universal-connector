from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ap_speed_test import ApSpeedTestError, project_ap_speed_test
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE_REF, AP_REF, PEER_REF = "a" * 24, "b" * 24, "c" * 24
AP_MAC, PEER_MAC = "00:11:22:33:44:55", "00-11-22-33-44-66"


def _sample() -> dict[str, object]:
    return {
        "mainTesting": False,
        "sourceAP": AP_MAC,
        "targetAP": PEER_MAC,
        "speedTestResult": {
            "uplink": {"role": 0, "downRate": 100.5, "upRate": 20.25,
                       "time": 1_800_000_000_000, "status": 1},
            "downlink": {"role": 1, "downRate": 90, "upRate": 18,
                         "time": 1_800_000_000_100, "status": 1},
        },
    }


class ApSpeedTestProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.refs = {"001122334455": AP_REF, "001122334466": PEER_REF}

    def test_projects_both_documented_map_and_single_object_forms(self) -> None:
        mapped = project_ap_speed_test(_sample(), AP_REF, self.refs)
        self.assertFalse(mapped["partial"])
        self.assertEqual(mapped["data"]["source_ap_ref"], AP_REF)
        self.assertEqual(mapped["data"]["target_ap_ref"], PEER_REF)
        self.assertEqual([row["role"] for row in mapped["data"]["results"]], [0, 1])
        single = _sample()
        single["speedTestResult"] = _sample()["speedTestResult"]["uplink"]
        self.assertEqual(len(project_ap_speed_test(single, AP_REF, self.refs)["data"]["results"]), 1)
        for secret in (AP_MAC, PEER_MAC, "uplink", "downlink"):
            self.assertNotIn(secret, repr(mapped))

    def test_unmapped_addresses_and_error_messages_are_removed_and_mark_partial(self) -> None:
        value = _sample()
        value["targetAP"] = "02:00:00:00:00:01"
        value["speedTestResult"] = {"uplink": {
            "role": 0, "downRate": 1, "upRate": 2, "time": 3,
            "status": -1, "errorCode": -7, "errorMsg": "private MAC",
        }}
        result = project_ap_speed_test(value, AP_REF, self.refs)
        self.assertTrue(result["partial"])
        self.assertNotIn("target_ap_ref", result["data"])
        self.assertEqual(result["data"]["results"][0]["error_code"], -7)
        self.assertNotIn("private MAC", repr(result))

    def test_rejects_unbounded_or_wrong_root_shapes_and_marks_bad_samples_partial(self) -> None:
        for value in (None, [], {str(index): 0 for index in range(17)},
                      {"mainTesting": False, "speedTestResult": {str(i): {} for i in range(5)}}):
            with self.subTest(value=value), self.assertRaises(ApSpeedTestError):
                project_ap_speed_test(value, AP_REF, self.refs)
        malformed = _sample()
        malformed["speedTestResult"] = {"result": {
            "role": True, "downRate": float("inf"), "upRate": -1,
            "time": -1, "status": 5,
        }}
        self.assertTrue(project_ap_speed_test(malformed, AP_REF, self.refs)["partial"])


class ApSpeedTestClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        self.client._site_ids_by_ref[SITE_REF] = "site_1"
        self.client._device_macs_by_site_ref[SITE_REF] = {
            AP_REF: AP_MAC, PEER_REF: PEER_MAC,
        }

    def test_reads_exact_fixed_route_and_returns_only_opaque_ap_refs(self) -> None:
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": _sample()}) as request:
            result = self.client.read_ap_speed_test_results(SITE_REF, AP_REF)
        request.assert_called_once_with(
            "GET", f"/openapi/v1/ctrl/sites/site_1/aps/{AP_MAC}/speed-test-result",
            token="token")
        self.assertEqual(result["resource"], "ap_speed_test_results")
        self.assertEqual(result["data"]["target_ap_ref"], PEER_REF)
        self.assertNotIn(AP_MAC, repr(result))
        self.assertNotIn(PEER_MAC, repr(result))

    def test_fixed_route_allowlist_and_inventory_binding(self) -> None:
        route = f"/openapi/v1/ctrl/sites/site_1/aps/{AP_MAC}/speed-test-result"
        with patch.object(self.client, "_connection", side_effect=OpenApiError("connection_reached")):
            with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                self.client._request_json("GET", route)
        for invalid in (route + "?x=1", route.replace("/ctrl/", "/other/"),
                        route.replace(AP_MAC, "evil")):
            with self.subTest(path=invalid), self.assertRaisesRegex(
                    OpenApiError, "openapi_path_rejected"):
                self.client._request_json("GET", invalid)
        with self.assertRaisesRegex(OpenApiError, "device_ref_unknown"):
            self.client.read_ap_speed_test_results(SITE_REF, "d" * 24)


if __name__ == "__main__":
    unittest.main()
