import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig


class SiteIotRadioIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.site_ref = "a" * 24
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_uses_fixed_route_and_redacts_passcode(self):
        payload = {"enable": True, "consoleMode": 1, "passcode": "987654",
                   "transmitPower": 0}
        with patch.object(self.client, "_resolve_site_ref", return_value=self.site_ref), \
                patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": payload}) as req:
            result = self.client.read_site_iot_radio_summary(self.site_ref)
        req.assert_called_once_with(
            "GET", "/openapi/v1/ctrl/sites/" + self.site_ref + "/setting/iot/radio",
            token="token")
        self.assertEqual(result["data"]["console_mode"], "on")
        self.assertTrue(result["data"]["passcode_configured"])
        self.assertNotIn("987654", repr(result))


if __name__ == "__main__":
    unittest.main()
