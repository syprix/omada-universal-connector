import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteIotTransmitPowerIntegrationTests(unittest.TestCase):
    def test_fixed_page_route_and_redacted_projection(self):
        site_ref = "a" * 24
        client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))
        payload = {"totalRows": 1, "currentPage": 1, "currentSize": 100,
                   "data": [{"mac": "aa:bb:cc:dd:ee:ff", "transmitPower": 5,
                             "statusCategory": 1, "override": True}]}
        with patch.object(client, "_resolve_site_ref", return_value=site_ref), \
                patch.object(client, "_access_token", return_value="token"), \
                patch.object(client, "_request_json", return_value={"result": payload}) as req:
            result = client.read_site_iot_transmit_power_summary(site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + site_ref
            + "/setting/iot/radio/transmit-power?page=1&pageSize=100", token="token")
        self.assertEqual(result["data"]["transmit_power_device_counts_dbm"], {"5": 1})
        self.assertNotIn("aa:bb:cc:dd:ee:ff", repr(result))


if __name__ == "__main__":
    unittest.main()
