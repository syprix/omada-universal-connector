import unittest
from unittest.mock import patch

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class MspCustomerRolesIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "client-id", "client-secret",
            cert_sha256="a" * 64))

    def test_fixed_cbc_path_and_aggregate_projection(self):
        rows = [{"name": "private-role", "id": "secret-id", "type": 1,
                 "defaultRole": True, "source": 2, "privilege": {"hidden": True}}]
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": rows}) as request:
            result = self.client.read_msp_customer_roles("msp-1")
        request.assert_called_once_with(
            "GET", "/openapi/v1/msp/msp-1/customer-roles", token="token")
        self.assertEqual(result["resource"], "msp_customer_roles")
        self.assertEqual(result["data"]["role_count"], 1)
        for private in ("private-role", "secret-id", "hidden"):
            self.assertNotIn(private, str(result))
        with self.assertRaisesRegex(OpenApiError, "msp_reference_invalid"):
            self.client.read_msp_customer_roles("../msp")

    def test_bad_response_shape_is_rejected(self):
        with patch.object(self.client, "_access_token", return_value="token"), \
                patch.object(self.client, "_request_json", return_value={"result": {}}):
            with self.assertRaisesRegex(OpenApiError, "openapi_response_invalid"):
                self.client.read_msp_customer_roles("msp-1")


if __name__ == "__main__":
    unittest.main()
