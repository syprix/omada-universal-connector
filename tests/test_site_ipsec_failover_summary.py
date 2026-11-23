from __future__ import annotations

import unittest

from app.site_ipsec_failover_summary import (
    IpsecFailoverSummaryError, project_ipsec_failover_page,
)


class IpsecFailoverSummaryTests(unittest.TestCase):
    def test_counts_only_reference_and_setting_metadata(self):
        result = project_ipsec_failover_page({
            "errorCode": 0, "msg": "", "result": {
                "totalRows": 1, "currentPage": 1, "currentSize": 1,
                "data": [{"id": "private-id", "name": "private-name",
                          "primary": {"id": "private-primary", "name": "vpn",
                                      "status": 0},
                          "candidates": [{"id": "private-candidate", "status": 1}],
                          "failBack": True, "failBackTime": 123}],
            }}, expected_page=1, page_size=2, max_rows=1000)
        self.assertEqual(result["rows"], 1)
        self.assertEqual(result["primary_reference_count"], 1)
        self.assertEqual(result["candidate_reference_count"], 1)
        self.assertEqual(result["failback_enabled_count"], 1)
        self.assertEqual(result["failback_time_field_present_count"], 1)
        self.assertNotIn("private", str(result))

    def test_caps_projection_without_changing_the_page_size(self):
        rows = [{"primary": {}, "candidates": [], "failBack": False}
                for _ in range(3)]
        result = project_ipsec_failover_page({
            "errorCode": 0, "msg": "", "result": {
                "totalRows": 3, "currentPage": 1, "currentSize": 3,
                "data": rows,
            }}, expected_page=1, page_size=3, max_rows=2)
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["primary_reference_count"], 2)

    def test_rejects_invalid_envelope_page_and_raw_fields(self):
        invalid = (
            {"errorCode": 1, "msg": "", "result": {}},
            {"errorCode": 0, "msg": "", "result": {"totalRows": 1,
             "currentPage": 2, "currentSize": 1, "data": [{}]}},
            {"errorCode": 0, "msg": "", "result": {"totalRows": 1,
             "currentPage": 1, "currentSize": 1, "data": [{"ip": "secret"}]}},
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                with self.assertRaises(IpsecFailoverSummaryError):
                    project_ipsec_failover_page(payload, 1, 10, 10)


if __name__ == "__main__":
    unittest.main()
