import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteClientAssociationTimeIntegrationTests(unittest.TestCase):
    def test_fixed_trailing_day_read_route(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        result_payload = {"lessThan2sNum": 5, "from2To4sNum": 0, "from4To6sNum": 0,
                          "from6To8sNum": 0, "from8To10sNum": 0,
                          "moreThan10sNum": 0, "fails": 1, "lessThan10sPercent": 83}
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch("app.openapi.datetime") as clock, \
                patch.object(client, "_request_json", return_value={"result": result_payload}) as req:
            clock.now.return_value.timestamp.return_value = 2_000_000_000
            result = client.read_site_client_association_time_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref
            + "/dashboard/client-association-time-distribution?start=1999913600&end=2000000000",
            token="token")
        self.assertEqual(result["window_end_seconds"], 2_000_000_000)
        self.assertEqual(result["data"]["failed_association_count"], 1)


if __name__ == "__main__":
    unittest.main()
