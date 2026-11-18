from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

from app.openapi import OpenApiError
from tools import controller_probe


class FakeReader:
    def __init__(self, result: object = None, error: Exception | None = None) -> None:
        self.result = result if result is not None else {
            "status": "ok", "resource": "sites", "count": 2,
            "items": [{"site_ref": "private-site-reference"}],
        }
        self.error = error
        self.calls = 0

    def list_sites(self) -> dict[str, object]:
        self.calls += 1
        if self.error:
            raise self.error
        return self.result  # type: ignore[return-value]


class ControllerProbeTests(unittest.TestCase):
    def test_probe_returns_only_reachability_count_and_read_only_flag(self) -> None:
        reader = FakeReader()
        output = controller_probe.probe(reader)
        self.assertEqual(output, {
            "status": "ok", "controller": "reachable", "site_count": 2,
            "read_only": True,
        })
        self.assertEqual(reader.calls, 1)
        self.assertNotIn("private-site-reference", json.dumps(output))

    def test_probe_rejects_invalid_count(self) -> None:
        for value in (True, -1, "2", None):
            with self.subTest(value=value), self.assertRaisesRegex(
                    OpenApiError, "openapi_response_invalid"):
                controller_probe.probe(FakeReader({"count": value}))

    def test_cli_uses_configured_client_and_prints_only_aggregate_result(self) -> None:
        reader = FakeReader()
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(controller_probe.OpenApiConfig, "from_env", return_value=object()), \
                patch.object(controller_probe, "OmadaOpenApiClient", return_value=reader) as make_client, \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = controller_probe.main()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), {
            "status": "ok", "controller": "reachable", "site_count": 2,
            "read_only": True,
        })
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(reader.calls, 1)
        make_client.assert_called_once_with(unittest.mock.ANY)
        self.assertNotIn("private-site-reference", stdout.getvalue())

    def test_cli_sanitizes_controller_and_unexpected_errors(self) -> None:
        for error, expected in (
            (OpenApiError("openapi_authentication_failed"), "openapi_authentication_failed"),
            (RuntimeError("secret-value-must-not-leak"), "controller_probe_failed"),
        ):
            reader = FakeReader(error=error)
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(error=type(error).__name__), \
                    patch.object(controller_probe.OpenApiConfig, "from_env", return_value=object()), \
                    patch.object(controller_probe, "OmadaOpenApiClient", return_value=reader), \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = controller_probe.main()
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(stdout.getvalue()), {
                "status": "error", "error": expected, "read_only": True,
            })
            self.assertEqual(stderr.getvalue(), "")
            self.assertNotIn("secret-value-must-not-leak", stdout.getvalue())

    def test_image_includes_controller_probe_entrypoint(self) -> None:
        dockerfile = os.path.join(os.path.dirname(__file__), "..", "Dockerfile")
        with open(dockerfile, encoding="utf-8") as stream:
            self.assertIn("COPY tools/controller_probe.py /app/tools/controller_probe.py",
                          stream.read())


if __name__ == "__main__":
    unittest.main()
