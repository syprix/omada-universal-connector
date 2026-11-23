from __future__ import annotations

import unittest

from app.controller_upgrade_failed_device_summary import (
    UpgradeFailureSummaryError, project_failed_device_page,
    project_upgrade_log_inventory_page,
)


class ControllerUpgradeFailedDeviceSummaryTests(unittest.TestCase):
    def test_accepts_only_documented_empty_upgrade_log_placeholder(self):
        result = {"totalRows": 0, "currentPage": 0, "currentSize": 0,
                  "data": [{"id": "", "modelTypeInfo": {"showModel": "", "compoundModel": ""},
                            "siteNames": [], "siteNum": 0, "currentVersion": [],
                            "targetVersion": "", "upgradeTime": "", "operator": "",
                            "rollbacked": True, "failedDeviceNum": 0}]}
        projected = project_upgrade_log_inventory_page(result, 1, 100, lambda _: "x" * 24)
        self.assertEqual(projected["total_rows"], 0)
        result["data"][0]["id"] = "unexpected"
        with self.assertRaises(UpgradeFailureSummaryError):
            project_upgrade_log_inventory_page(result, 1, 100, lambda _: "x" * 24)

    def test_inventory_returns_only_unique_opaque_references(self):
        result = project_upgrade_log_inventory_page(
            {"totalRows": 3, "currentPage": 1, "currentSize": 3,
             "data": [{"id": "log-one", "name": "secret"},
                      {"id": "log-one", "name": "duplicate"},
                      {"name": "missing-id"}]},
            1, 100, lambda raw: "r" * 23 + str(len(raw) % 10))
        self.assertEqual(result["rows"], 3)
        self.assertEqual(result["selectable_log_count"], 0)
        self.assertEqual(result["unselectable_log_count"], 1)
        self.assertEqual(result["ambiguous_log_reference_count"], 1)
        self.assertNotIn("log-one", str(result))

    def test_counts_only_documented_device_types(self):
        result = project_failed_device_page({
            "errorCode": 0, "msg": "", "result": {
                "totalRows": 4, "currentPage": 1, "currentSize": 4,
                "data": [
                    {"type": "gateway", "mac": "secret", "deviceName": "private"},
                    {"type": "switch", "currentVersion": "1.0"},
                    {"type": "ap", "siteName": "private-site"},
                    {"type": "unknown-vendor-type"},
                ],
            }}, 1, 100, 1_000)
        self.assertEqual(result["device_type_counts"],
                         {"gateway": 1, "switch": 1, "ap": 1, "unknown": 1})
        self.assertNotIn("secret", str(result))
        self.assertNotIn("1.0", str(result))

    def test_accepts_only_the_documented_empty_placeholder(self):
        payload = {"errorCode": 0, "msg": "", "result": {
            "totalRows": 0, "currentPage": 0, "currentSize": 0,
            "data": [{"modelTypeInfo": {"showModel": "", "compoundModel": ""},
                      "deviceName": "", "mac": "", "currentVersion": "",
                      "siteName": "", "type": ""}],
        }}
        result = project_failed_device_page(payload, 1, 100, 1_000)
        self.assertEqual(result["rows"], 0)
        self.assertEqual(result["device_type_counts"]["unknown"], 0)
        payload["result"]["data"][0]["mac"] = "not-empty"
        with self.assertRaises(UpgradeFailureSummaryError):
            project_failed_device_page(payload, 1, 100, 1_000)

    def test_rejects_invalid_page_and_raw_extra_fields(self):
        for payload in (
            {"errorCode": 0, "msg": "", "result": {"totalRows": 1,
             "currentPage": 2, "currentSize": 1, "data": [{"type": "ap"}]}},
            {"errorCode": 0, "msg": "", "result": {"totalRows": 1,
             "currentPage": 1, "currentSize": 1, "data": [{"secret": "value"}]}},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(UpgradeFailureSummaryError):
                    project_failed_device_page(payload, 1, 100, 100)


if __name__ == "__main__":
    unittest.main()
