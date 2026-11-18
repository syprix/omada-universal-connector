import unittest

from app.site_gateway_isp_summary import (
    SiteGatewayIspSummaryError, project_site_gateway_isp_summary,
)


class SiteGatewayIspSummaryTests(unittest.TestCase):
    def test_projects_status_and_peak_utilization_without_wan_identifiers(self):
        result = project_site_gateway_isp_summary({"data": [{
            "name": "private-gateway", "mac": "gateway-id", "status": 1,
            "ispInfo": {"type": 1, "ispArr": [{"name": "private-isp", "ip": "private-ip",
                "status": 1, "onLineStatus": 1, "uploadPercent": 25.5,
                "downloadPercent": 81.25, "port": 2}]},
        }]})
        self.assertFalse(result["partial"])
        self.assertEqual(result["data"]["gateway_status_counts"]["active"], 1)
        self.assertEqual(result["data"]["online_isp_count"], 1)
        self.assertEqual(result["data"]["maximum_download_utilization_percent"], 81.25)
        for value in ("private-gateway", "gateway-id", "private-isp", "private-ip"):
            self.assertNotIn(value, repr(result))

    def test_flags_invalid_and_unknown_fields_and_bounds_gateway_rows(self):
        result = project_site_gateway_isp_summary({"data": [{"status": 4, "extra": "hidden"}]})
        self.assertEqual(result["invalid_field_count"], 1)
        self.assertEqual(result["unknown_field_count"], 1)
        self.assertNotIn("hidden", repr(result))
        with self.assertRaises(SiteGatewayIspSummaryError):
            project_site_gateway_isp_summary({"data": [{}] * 21})


if __name__ == "__main__":
    unittest.main()
