from __future__ import annotations

import unittest
from unittest.mock import patch

from app.device_adoption_summary import DeviceAdoptionSummaryError, summarize_adoption_devices
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class AdoptionSummaryProjectionTests(unittest.TestCase):
    def test_batch_adopt_array_is_reduced_to_bounded_counts(self) -> None:
        result = summarize_adoption_devices([
            {"type": "AP", "mac": "private-mac", "name": "private-name", "model": "private-model",
             "status": 1, "licenseStatus": 0, "compatible": 1, "deviceSeriesType": 0,
             "inWhitelist": True, "wireless": True},
            {"type": "switch", "mac": "other-private-mac", "status": 2,
             "licenseStatus": 1, "compatible": 0, "deviceSeriesType": 1,
             "inWhitelist": False, "wireless": False},
        ], kind="batch", page_size=10)
        self.assertEqual(result["data"]["sampled_count"], 2)
        self.assertEqual(result["data"]["type_counts"], {"access_point": 1, "switch": 1})
        self.assertEqual(result["data"]["status_code_counts"], {"1": 1, "2": 1})
        self.assertEqual(result["data"]["license_status_code_counts"], {"0": 1, "1": 1})
        self.assertFalse(result["partial"])
        for private in ("private-mac", "private-name", "private-model", "other-private-mac"):
            self.assertNotIn(private, repr(result))

    def test_site_pending_grid_tracks_total_and_redacts_device_details(self) -> None:
        result = summarize_adoption_devices({
            "totalRows": 3, "currentPage": 1, "currentSize": 2,
            "data": [
                {"type": "gateway", "status": 0, "licenseStatus": 1, "compatible": 1,
                 "deviceSeriesType": 0, "ip": "192.0.2.10", "sn": "private-serial"},
                {"type": "unrecognized", "status": 99, "licenseStatus": 0,
                 "compatible": 0, "deviceSeriesType": 1, "name": "private-device"},
            ],
        }, kind="pending", page_size=2)
        self.assertEqual(result["data"]["device_count"], 3)
        self.assertEqual(result["data"]["sampled_count"], 2)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["type_counts"], {"gateway": 1, "other": 1})
        self.assertEqual(result["data"]["unknown_value_count"], 1)
        for private in ("192.0.2.10", "private-serial", "private-device"):
            self.assertNotIn(private, repr(result))

    def test_invalid_response_shapes_values_and_page_bounds_fail_closed(self) -> None:
        for kind, payload, page_size in (
            ("batch", {"result": []}, 10),
            ("pending", {"totalRows": 0, "currentPage": 2, "currentSize": 0, "data": []}, 10),
            ("pending", {"totalRows": 0, "currentPage": 1, "currentSize": 0, "data": []}, 0),
            ("other", [], 10),
        ):
            with self.subTest(kind=kind, payload=payload):
                with self.assertRaises(DeviceAdoptionSummaryError):
                    summarize_adoption_devices(payload, kind=kind, page_size=page_size)
        partial = summarize_adoption_devices([
            {"type": 7, "status": "bad", "unexpected": "private"}, None,
        ], kind="batch", page_size=10)
        self.assertTrue(partial["partial"])
        self.assertEqual(partial["data"]["invalid_count"], 3)
        self.assertEqual(partial["data"]["unknown_field_count"], 1)
        self.assertNotIn("private", repr(partial))


class AdoptionSummaryClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64,
            page_size=32))
        self.site_ref = "a" * 24
        self.client._site_ids_by_ref[self.site_ref] = "site-1"

    def test_reads_use_fixed_page_and_project_only_summaries(self) -> None:
        payloads = (
            (self.client.read_controller_device_batch_adopt_summary,
             "/openapi/v1/ctrl/devices/batch/info?page=1&pageSize=32",
             [{"type": "ap", "mac": "private-mac", "status": 1, "licenseStatus": 0,
               "compatible": 1, "deviceSeriesType": 0}]),
            (lambda: self.client.read_site_pending_devices_summary(self.site_ref),
             "/openapi/v1/ctrl/sites/site-1/grid/devices/pending?page=1&pageSize=32",
             {"totalRows": 1, "currentPage": 1, "currentSize": 1,
              "data": [{"type": "ap", "mac": "private-mac", "status": 1,
                        "licenseStatus": 0, "compatible": 1, "deviceSeriesType": 0}]}),
        )
        resources = ("controller_device_batch_adopt_summary", "site_pending_devices_summary")
        for (method, path, result), resource in zip(payloads, resources):
            with self.subTest(resource=resource), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": result}) as request:
                projected = method()
            request.assert_called_once_with("GET", path, token="token")
            self.assertEqual(projected["resource"], resource)
            self.assertNotIn("private-mac", repr(projected))

    def test_paths_are_bound_to_controller_page_size_and_resolved_site(self) -> None:
        paths = (
            "/openapi/v1/ctrl/devices/batch/info?page=1&pageSize=32",
            "/openapi/v1/ctrl/sites/site-1/grid/devices/pending?page=1&pageSize=32",
        )
        for path in paths:
            with self.subTest(path=path), patch.object(
                    self.client, "_connection", side_effect=OpenApiError("connection_reached")):
                with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                    self.client._request_json("GET", path)
        invalid_paths = (
            paths[0].replace("/ctrl/", "/other/"),
            paths[0].replace("page=1", "page=2"),
            paths[0].replace("pageSize=32", "pageSize=33"),
            paths[0] + "&searchKey=caller-value",
            paths[1].replace("site-1", "other-site"),
            paths[1].replace("pageSize=32", "pageSize=33"),
        )
        for path in invalid_paths:
            with self.subTest(path=path), patch.object(self.client, "_connection") as connection:
                with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                    self.client._request_json("GET", path)
                connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
