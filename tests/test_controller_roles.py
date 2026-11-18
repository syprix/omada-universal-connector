from __future__ import annotations

import unittest
from unittest.mock import patch

from app.controller_roles import (
    ControllerRolesError, project_controller_roles,
)
from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError


class ControllerRoleProjectionTests(unittest.TestCase):
    """Fixture coverage for controller_roles and controller_available_roles."""

    def test_controller_roles_returns_only_bounded_category_counts(self) -> None:
        result = project_controller_roles([{
            "id": "private-role-id", "name": "Private Admin", "type": 0,
            "defaultRole": True, "source": 0,
            "privilege": {"devices": 2, "roles": 1, "network": 0},
        }], includes_privilege=True)
        data = result["data"]
        self.assertEqual(data["role_count"], 1)
        self.assertEqual(data["type_counts"], {"standard": 1})
        self.assertEqual(data["source_counts"], {"default": 1})
        self.assertEqual(data["permission_code_counts"], {"0": 1, "1": 1, "2": 1})
        self.assertFalse(result["partial"])
        for private in ("private-role-id", "Private Admin", "devices", "network"):
            self.assertNotIn(private, repr(result))

    def test_controller_available_roles_omits_privilege_counts(self) -> None:
        result = project_controller_roles([{
            "id": "private-id", "name": "Private role", "type": 1,
            "defaultRole": False, "source": 1,
        }], includes_privilege=False)
        self.assertEqual(result["data"]["type_counts"], {"customer": 1})
        self.assertIsNone(result["data"]["permission_code_counts"])
        self.assertFalse(result["partial"])
        self.assertNotIn("private-id", repr(result))
        self.assertNotIn("Private role", repr(result))

    def test_unknown_and_invalid_fields_mark_summary_partial(self) -> None:
        result = project_controller_roles([{
            "id": "id", "name": "name", "type": 8, "defaultRole": "yes",
            "source": 0, "privilege": {"private": 7}, "future": "drop",
        }], includes_privilege=True)
        self.assertTrue(result["partial"])
        self.assertEqual(result["data"]["unknown_field_count"], 3)
        self.assertGreater(result["data"]["invalid_count"], 0)
        self.assertNotIn("drop", repr(result))
        with self.assertRaises(ControllerRolesError):
            project_controller_roles([{}] * 501, includes_privilege=False)


class ControllerRoleReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OmadaOpenApiClient(OpenApiConfig(
            "https://controller.example", "ctrl", "id", "secret", cert_sha256="a" * 64))

    def test_controller_roles_use_the_exact_fixed_get_paths(self) -> None:
        cases = (
            (self.client.read_controller_roles, "/openapi/v1/ctrl/roles",
             [{"id": "private", "name": "hidden", "type": 0,
               "defaultRole": True, "source": 0, "privilege": {"devices": 1}}],
             "controller_roles"),
            (self.client.read_controller_available_roles, "/openapi/v1/ctrl/roles/available",
             [{"id": "private", "name": "hidden", "type": 0,
               "defaultRole": True, "source": 0}], "controller_available_roles"),
        )
        for method, path, response, resource in cases:
            with self.subTest(resource=resource), \
                    patch.object(self.client, "_access_token", return_value="token"), \
                    patch.object(self.client, "_request_json", return_value={"result": response}) as request:
                result = method()
            request.assert_called_once_with("GET", path, token="token")
            self.assertEqual(result["resource"], resource)
            self.assertNotIn("private", repr(result))
            self.assertNotIn("hidden", repr(result))

    def test_controller_role_paths_are_allowlisted_and_controller_bound(self) -> None:
        self.assertTrue(self.client._controller_roles_request_valid("/openapi/v1/ctrl/roles"))
        self.assertTrue(self.client._controller_available_roles_request_valid(
            "/openapi/v1/ctrl/roles/available"))
        self.assertFalse(self.client._controller_roles_request_valid("/openapi/v1/other/roles"))
        self.assertFalse(self.client._controller_available_roles_request_valid(
            "/openapi/v1/ctrl/roles/available?path=/other"))
        for path in ("/openapi/v1/ctrl/roles", "/openapi/v1/ctrl/roles/available"):
            with self.subTest(path=path), patch.object(
                    self.client, "_connection", side_effect=OpenApiError("connection_reached")):
                with self.assertRaisesRegex(OpenApiError, "connection_reached"):
                    self.client._request_json("GET", path)
        with patch.object(self.client, "_connection") as connection:
            with self.assertRaisesRegex(OpenApiError, "openapi_path_rejected"):
                self.client._request_json("POST", "/openapi/v1/ctrl/roles")
        connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
