import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteApRssiDensityIntegrationTests(unittest.TestCase):
    def test_fixed_site_route_returns_redacted_counts(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        payload = {"existAp": True, "existApClient": False}
        buckets = ("lessThan90", "from90To85", "from85To80", "from80To75", "from75To70",
                   "from70To65", "from65To60", "from60To55", "from55To50", "from50To45",
                   "from45To40", "from40To35", "from35To30", "moreThan30")
        payload.update({field: [] for field in buckets})
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": payload}) as req:
            result = client.read_site_ap_rssi_density_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref + "/dashboard/ap-density", token="token")
        self.assertTrue(result["data"]["access_points_present"])
        self.assertEqual(result["data"]["ap_count_in_buckets"], 0)


if __name__ == "__main__":
    unittest.main()
