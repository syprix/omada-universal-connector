from __future__ import annotations

import unittest
from unittest.mock import patch

from app.device_firmware_summary import (
    DeviceFirmwareSummaryError, project_site_firmware_summary,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


SITE = "a" * 24
AP = "b" * 24
SWITCH = "c" * 24
GATEWAY = "d" * 24


def inventory() -> dict[str, object]:
    return {"status": "ok", "resource": "devices", "count": 3, "items": [
        {"device_ref": AP, "device_type": "Access Point", "model": "EAP650",
         "firmware": "1.0.0"},
        {"device_ref": SWITCH, "device_type": "Switch", "model": "SG2210P",
         "firmware": "2.0.0"},
        {"device_ref": GATEWAY, "device_type": "Gateway", "model": "ER7206"},
    ]}


def readings() -> dict[str, object]:
    return {
        AP: {"status": "ok", "resource": "device_firmware", "device_ref": AP,
             "data": {"current_version": "1.0.0", "latest_version": "1.0.0",
                      "versions_differ": False, "update_available": None}},
        SWITCH: {"status": "ok", "resource": "device_firmware", "device_ref": SWITCH,
                 "data": {"current_version": "2.0.0", "latest_version": "1.9.0",
                          "versions_differ": True, "update_available": None}},
        GATEWAY: {"status": "error", "error": "openapi_rejected"},
    }


class DeviceFirmwareSummaryTests(unittest.TestCase):
    def test_groups_model_versions_and_reports_only_evidence_based_status(self) -> None:
        result = project_site_firmware_summary(SITE, inventory(), readings())
        self.assertEqual(result["resource"], "site_firmware_summary")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["summary"], {
            "inventory_device_count": 3, "checked_device_count": 3,
            "omitted_device_count": 0, "model_firmware_group_count": 3,
            "firmware_status_counts": {"differs_from_latest": 1,
                                        "matches_latest": 1,
                                        "read_unavailable": 1},
        })
        statuses = {row["model"]: row["firmware_status"] for row in result["groups"]}
        self.assertEqual(statuses, {"EAP650": "matches_latest",
                                    "SG2210P": "differs_from_latest",
                                    "ER7206": "read_unavailable"})
        self.assertEqual(result["data_scope"]["version_ordering"],
                         "not_inferred_from_version_strings")
        self.assertNotIn(AP, str(result))
        self.assertNotIn(SWITCH, str(result))

    def test_marks_inventory_conflict_and_missing_versions_partial(self) -> None:
        values = readings()
        values[AP] = values[AP] | {"data": {"current_version": "1.0.1",
                                              "latest_version": None,
                                              "versions_differ": None,
                                              "update_available": None}}
        result = project_site_firmware_summary(SITE, inventory(), values)
        row = next(item for item in result["groups"] if item["model"] == "EAP650")
        self.assertEqual(row["firmware_status"], "inventory_disagrees")
        self.assertTrue(result["partial"])

    def test_caps_device_reads_and_rejects_bad_inventory_or_versions(self) -> None:
        inv = {"status": "ok", "resource": "devices", "count": 65,
               "items": [{"device_ref": f"{i:024x}", "device_type": "Switch",
                          "model": "SG2210P"} for i in range(1, 66)]}
        result = project_site_firmware_summary(SITE, inv, {})
        self.assertEqual(result["summary"]["checked_device_count"], 64)
        self.assertEqual(result["summary"]["omitted_device_count"], 1)
        self.assertTrue(result["partial"])
        with self.assertRaises(DeviceFirmwareSummaryError):
            project_site_firmware_summary(SITE, {**inv, "count": 66}, {})
        bad = readings()
        bad[AP] = bad[AP] | {"data": {"current_version": "https://example.invalid/fw",
                                        "latest_version": "1.0", "update_available": None}}
        with self.assertRaises(DeviceFirmwareSummaryError):
            project_site_firmware_summary(SITE, inventory(), bad)

    def test_client_composes_site_inventory_with_only_bounded_firmware_reads(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site-1"
        with patch.object(client, "list_devices", return_value=inventory()), \
                patch.object(client, "read_device_firmware", side_effect=[
                    readings()[AP], readings()[SWITCH], OpenApiError("openapi_rejected")
                ]) as read:
            result = client.read_site_firmware_summary(SITE)
        self.assertEqual(result["resource"], "site_firmware_summary")
        self.assertEqual(read.call_count, 3)
        self.assertTrue(all(call.args[0] == SITE for call in read.call_args_list))

    def test_client_rejects_unknown_site_without_controller_reads(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        with self.assertRaisesRegex(OpenApiError, "site_ref_unknown"):
            client.read_site_firmware_summary(SITE)

    def test_client_never_reads_more_than_the_first_64_devices(self) -> None:
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))
        client._site_ids_by_ref[SITE] = "site-1"
        rows = [{"device_ref": f"{i:024x}", "device_type": "Switch", "model": "SG2210P"}
                for i in range(1, 66)]
        listing = {"status": "ok", "resource": "devices", "count": len(rows), "items": rows}
        def response_for(_site_ref, ref):
            return {"status": "ok", "resource": "device_firmware", "device_ref": ref,
                    "data": {"current_version": "1.0", "latest_version": "1.0",
                             "versions_differ": False, "update_available": None}}
        with patch.object(client, "list_devices", return_value=listing), \
                patch.object(client, "read_device_firmware", side_effect=response_for) as read:
            result = client.read_site_firmware_summary(SITE)
        self.assertEqual(read.call_count, 64)
        self.assertEqual(result["summary"]["omitted_device_count"], 1)
        self.assertTrue(result["partial"])


if __name__ == "__main__":
    unittest.main()
