import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteClientRssiDistributionIntegrationTests(unittest.TestCase):
    def test_fixed_route_and_band_aggregates(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        counts = {"lessThan72": 1, "from71To65": 2, "from65To55": 3,
                  "from55To45": 4, "moreThan45": 5}
        payload = {**counts, "distribution2G": counts, "distribution5G": counts,
                   "distribution6G": counts}
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": payload}) as req:
            result = client.read_site_client_rssi_distribution_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/client-rssi-distribution", token="token")
        self.assertEqual(result["data"]["band_5_ghz"]["from_65_to_55"], 3)


if __name__ == "__main__":
    unittest.main()
