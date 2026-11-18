import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteBeaconControlIntegrationTests(unittest.TestCase):
    def test_fixed_read_route_and_projection(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        result_body = {"beaconControl": {
            "dtimPeriod2g": 2, "rtsThreshold2g": 2347,
            "dtimPeriod5g": 2, "rtsThreshold5g": 2347,
            "dtimPeriod6g": 2, "rtsThreshold6g": 2347},
            "airtimeFairness": {"enable2g": True, "enable5g": True, "enable6g": False}}
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": result_body}) as req:
            result = client.read_site_beacon_control_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref + "/beacon-control", token="token")
        self.assertEqual(result["resource"], "site_beacon_control_summary")
        self.assertTrue(result["data"]["airtime_fairness_enabled_2g"])


if __name__ == "__main__":
    unittest.main()
