#!/usr/bin/env python3
"""Check connector setup layers without exposing credentials or controller data."""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import stat
import sys
from typing import Any
from urllib.parse import urlsplit


PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError  # noqa: E402


_MCP_REQUEST_ID = "setup-check"
_MAX_MCP_RESPONSE_BYTES = 131_072
_MESSAGES = {
    "configuration": "Connector-Konfiguration und Zugangsdatenpfade",
    "tls": "TLS-Verbindung und Zertifikatsprüfung zum Controller",
    "authentication": "Omada-Anmeldung per Client-Zugang",
    "read_permission": "Leserecht auf das Standortinventar",
    "mcp": "MCP-Handshake, Werkzeugliste, sicherer Leseaufruf und Fehlerpfad",
}
_EXPLANATIONS = {
    "openapi_configuration_missing": "Erforderliche Controller-Einstellungen fehlen.",
    "openapi_configuration_invalid": "Eine Controller-Einstellung ist ungültig.",
    "controller_url_invalid": "Die Controller-Adresse muss eine gültige HTTPS-Adresse sein.",
    "controller_certificate_changed": "Der Controller-Zertifikat-Fingerabdruck stimmt nicht.",
    "controller_certificate_pin_required": "Für den Zertifikatsmodus fehlt der SHA-256-Fingerabdruck.",
    "controller_certificate_pin_invalid": "Der Zertifikats-Fingerabdruck hat ein ungültiges Format.",
    "controller_unreachable": "Der Controller oder sein TLS-Endpunkt ist nicht erreichbar.",
    "openapi_authentication_failed": "Der Controller hat die Anmeldung abgelehnt.",
    "openapi_permission_denied": "Das Omada-Konto darf das Standortinventar nicht lesen.",
    "openapi_response_invalid": "Die Inventarantwort entspricht nicht dem erwarteten Format.",
    "credential_file_not_configured": "Pfad zu Client-ID- oder Client-Geheimnisdatei fehlt.",
    "credential_file_unavailable": "Client-ID- oder Client-Geheimnisdatei ist nicht lesbar.",
    "credential_file_invalid": "Client-Zugangsdaten-Datei hat ein ungültiges Format.",
    "connector_token_not_configured": "Für den MCP-Test ist keine Connector-Zugangsdatei eingerichtet.",
    "connector_token_invalid": "Die Connector-Zugangsdatei ist ungültig oder nicht privat genug gespeichert.",
    "connector_url_invalid": "Die Connector-Adresse ist ungültig oder für unverschlüsselte Übertragung nicht lokal.",
    "connector_unreachable": "Der Connector ist unter der eingestellten Adresse nicht erreichbar.",
    "connector_tls_failed": "Die TLS-Prüfung für die HTTPS-Verbindung zum Connector ist fehlgeschlagen.",
    "connector_authentication_failed": "Der Connector hat den MCP-Aufruf abgelehnt; Zugang und Token prüfen.",
    "mcp_handshake_invalid": "Der Connector hat keine gültige MCP-Initialize-Antwort geliefert.",
    "mcp_handshake_rejected": "Der Connector hat den MCP-Handshake abgelehnt.",
    "mcp_tools_list_invalid": "Die MCP-Werkzeugliste fehlt oder ist ungültig.",
    "mcp_safe_read_failed": "Der harmlose MCP-Leseaufruf ist fehlgeschlagen.",
    "mcp_error_handling_failed": "Der erwartete MCP-Fehler wurde nicht sicher zurückgegeben.",
}


def _check(name: str, status: str, code: str | None = None,
           detail: str | None = None, **facts: object) -> dict[str, object]:
    result: dict[str, object] = {"name": name, "status": status}
    if code:
        result["code"] = code
        result["detail"] = detail or _EXPLANATIONS.get(code, "Der geprüfte Schritt ist fehlgeschlagen.")
    elif detail:
        result["detail"] = detail
    result.update(facts)
    return result


def _failure_code(exc: BaseException) -> str:
    return exc.code if isinstance(exc, OpenApiError) else "controller_unreachable"


def _controller_checks(client: Any | None, config_error: str | None) -> list[dict[str, object]]:
    if config_error is not None or client is None:
        code = config_error or "openapi_configuration_invalid"
        return [
            _check("tls", "not_run", code, "Zuerst die Controller-Konfiguration korrigieren."),
            _check("authentication", "not_run", code, "Zuerst die Controller-Konfiguration korrigieren."),
            _check("read_permission", "not_run", code, "Zuerst die Controller-Konfiguration korrigieren."),
        ]

    checks: list[dict[str, object]] = []
    try:
        connection = client._connection()
        connection.close()
        checks.append(_check("tls", "ok", detail="TLS-Verbindung und konfigurierte Vertrauensprüfung bestanden."))
    except Exception as exc:
        code = _failure_code(exc)
        checks.append(_check("tls", "error", code))
        checks.extend([
            _check("authentication", "not_run", "controller_tls_check_failed",
                   "Wegen des fehlgeschlagenen TLS-Schritts nicht ausgeführt."),
            _check("read_permission", "not_run", "controller_tls_check_failed",
                   "Wegen des fehlgeschlagenen TLS-Schritts nicht ausgeführt."),
        ])
        return checks

    try:
        if not (client.config.client_id_file and client.config.client_secret_file):
            raise OpenApiError("credential_file_not_configured")
        token = client._access_token()
        checks.append(_check("authentication", "ok", detail="Der Controller hat die Client-Anmeldung akzeptiert."))
    except Exception as exc:
        code = _failure_code(exc)
        checks.append(_check("authentication", "error", code))
        checks.append(_check("read_permission", "not_run", "controller_authentication_failed",
                             "Wegen der fehlgeschlagenen Anmeldung nicht ausgeführt."))
        return checks

    try:
        path = OmadaOpenApiClient._SITE_PATH.format(controller_id=client.config.controller_id)
        rows = client._read_pages(path, token)
        checks.append(_check("read_permission", "ok",
                             detail="Das Standortinventar ist lesbar.",
                             permission_scope="site_inventory", site_count=len(rows)))
    except Exception as exc:
        code = _failure_code(exc)
        checks.append(_check("read_permission", "error", code,
                             "Nur das Leserecht für das Standortinventar wurde geprüft."))
    return checks


def _read_connector_token(path: str | None) -> bytes:
    if not path:
        raise ValueError("connector_token_not_configured")
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("connector_token_invalid")
    fd = -1
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077 or
                info.st_size > 4096):
            raise ValueError("connector_token_invalid")
        token = os.read(fd, 4097).strip()
    except ValueError:
        raise
    except OSError:
        raise ValueError("connector_token_invalid") from None
    finally:
        if fd >= 0:
            os.close(fd)
    if (not 32 <= len(token) <= 4096 or
            any(byte < 0x21 or byte > 0x7e for byte in token)):
        raise ValueError("connector_token_invalid")
    return token


def _connector_address(value: str) -> tuple[str, str, int]:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (ValueError, AttributeError):
        raise ValueError("connector_url_invalid") from None
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or
            parsed.username or parsed.password or parsed.path not in ("", "/") or
            parsed.query or parsed.fragment or (port is not None and not 1 <= port <= 65535)):
        raise ValueError("connector_url_invalid")
    host = parsed.hostname.lower()
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme == "http" and host not in local_hosts:
        raise ValueError("connector_url_invalid")
    return parsed.scheme, host, port or (443 if parsed.scheme == "https" else 80)


class _McpCheckError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _mcp_check(connector_url: str, token_file: str | None) -> dict[str, object]:
    try:
        token = _read_connector_token(token_file)
        scheme, host, port = _connector_address(connector_url)
    except ValueError as exc:
        code = str(exc)
        return _check("mcp", "error", code)

    connection: http.client.HTTPConnection | http.client.HTTPSConnection | None = None
    try:
        if scheme == "https":
            connection = http.client.HTTPSConnection(
                host, port, timeout=3, context=ssl.create_default_context())
        else:
            connection = http.client.HTTPConnection(host, port, timeout=3)
        def exchange(request_id: str, method: str, params: dict[str, object]) -> dict[str, object]:
            body = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method,
                               "params": params}, separators=(",", ":")).encode("utf-8")
            connection.request("POST", "/mcp", body=body, headers={
                "Authorization": "Bearer " + token.decode("ascii"),
                "Content-Type": "application/json", "Accept": "application/json",
                "Connection": "close",
            })
            response = connection.getresponse()
            status = response.status
            content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
            raw = response.read(_MAX_MCP_RESPONSE_BYTES + 1)
            if status == 401:
                raise _McpCheckError("connector_authentication_failed")
            if status != 200:
                raise _McpCheckError("mcp_handshake_rejected")
            if content_type != "application/json" or len(raw) > _MAX_MCP_RESPONSE_BYTES:
                raise _McpCheckError("mcp_handshake_invalid")
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError, RecursionError):
                raise _McpCheckError("mcp_handshake_invalid") from None
            if (not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0" or
                    payload.get("id") != request_id):
                raise _McpCheckError("mcp_handshake_invalid")
            return payload

        initialized = exchange(f"{_MCP_REQUEST_ID}-initialize", "initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "omada-setup-check", "version": "1"},
        })
        result = initialized.get("result")
        if (not isinstance(result, dict) or result.get("protocolVersion") != "2025-06-18" or
                not isinstance(result.get("serverInfo"), dict) or
                result["serverInfo"].get("name") != "omada-universal-connector" or
                not isinstance(result["serverInfo"].get("version"), str)):
            return _check("mcp", "error", "mcp_handshake_invalid")

        tool_names: set[str] = set()
        safe_read_advertised = False
        cursor: str | None = None
        seen_cursors: set[str] = set()
        for page_number in range(64):
            params = {"cursor": cursor} if cursor is not None else {}
            page_payload = exchange(f"{_MCP_REQUEST_ID}-tools-{page_number}", "tools/list", params)
            page = page_payload.get("result")
            tools = page.get("tools") if isinstance(page, dict) else None
            if (not isinstance(tools, list) or len(tools) > 25 or
                    any(not isinstance(item, dict) or not isinstance(item.get("name"), str)
                        for item in tools)):
                return _check("mcp", "error", "mcp_tools_list_invalid")
            for item in tools:
                name = item["name"]
                tool_names.add(name)
                annotations = item.get("annotations")
                if name == "omada_sites" and isinstance(annotations, dict):
                    safe_read_advertised = annotations.get("readOnlyHint") is True
            next_cursor = page.get("nextCursor")
            if next_cursor is None:
                break
            if (not isinstance(next_cursor, str) or not next_cursor.isdigit() or
                    next_cursor in seen_cursors):
                return _check("mcp", "error", "mcp_tools_list_invalid")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        else:
            return _check("mcp", "error", "mcp_tools_list_invalid")
        if "omada_sites" not in tool_names or not safe_read_advertised:
            return _check("mcp", "error", "mcp_tools_list_invalid")

        safe_read = exchange(f"{_MCP_REQUEST_ID}-read", "tools/call", {
            "name": "omada_sites", "arguments": {},
        })
        read_result = safe_read.get("result")
        read_data = read_result.get("structuredContent") if isinstance(read_result, dict) else None
        if (not isinstance(read_result, dict) or read_result.get("isError") is True or
                not isinstance(read_data, dict) or read_data.get("status") != "ok" or
                read_data.get("resource") != "sites" or
                not isinstance(read_data.get("items"), list)):
            return _check("mcp", "error", "mcp_safe_read_failed")

        expected_error = exchange(f"{_MCP_REQUEST_ID}-error", "tools/call", {
            "name": "omada_setup_check_unknown", "arguments": {},
        }).get("error")
        if (not isinstance(expected_error, dict) or expected_error.get("code") != -32601 or
                expected_error.get("message") != "tool_unknown"):
            return _check("mcp", "error", "mcp_error_handling_failed")
        return _check(
            "mcp", "ok", detail="MCP-Initialisierung, Werkzeugliste, Standort-Leseaufruf und Fehlerantwort bestanden.",
            protocol_version=result["protocolVersion"], tool_count=len(tool_names),
            safe_read_tool="omada_sites", error_path="tool_unknown")
    except _McpCheckError as exc:
        return _check("mcp", "error", exc.code)
    except ssl.SSLError:
        return _check("mcp", "error", "connector_tls_failed")
    except (OSError, TimeoutError, http.client.HTTPException, ValueError, socket.gaierror):
        return _check("mcp", "error", "connector_unreachable")
    finally:
        if connection is not None:
            connection.close()


def run_setup_check(*, connector_url: str | None = None,
                    connector_token_file: str | None = None,
                    client: Any | None = None,
                    config_error: str | None = None) -> dict[str, object]:
    if client is None and config_error is None:
        try:
            base_url = os.getenv("OMADA_BASE_URL", "").strip()
            controller_id = os.getenv("OMADA_CONTROLLER_ID", "").strip()
            if not base_url or not controller_id:
                raise OpenApiError("openapi_configuration_missing")
            try:
                timeout = float(os.getenv("OMADA_TIMEOUT_SECONDS", "5"))
                page_size = int(os.getenv("OMADA_OPENAPI_PAGE_SIZE", "100"))
                max_pages = int(os.getenv("OMADA_OPENAPI_MAX_PAGES", "10"))
            except ValueError as exc:
                raise OpenApiError("openapi_configuration_invalid") from exc
            config = OpenApiConfig(
                base_url=base_url,
                controller_id=controller_id,
                client_id_file=os.getenv("OMADA_CLIENT_ID_FILE", "").strip(),
                client_secret_file=os.getenv("OMADA_CLIENT_SECRET_FILE", "").strip(),
                cert_sha256=os.getenv("OMADA_CERT_SHA256", "").strip().lower(),
                tls_trust=os.getenv("OMADA_TLS_TRUST", "pin_sha256").strip(),
                timeout_seconds=timeout, page_size=page_size, max_pages=max_pages,
                reference_key_file=os.getenv("OMADA_REFERENCE_KEY_FILE") or None,
                expose_descriptive_names=(os.getenv("OMADA_EXPOSE_DESCRIPTIVE_NAMES", "")
                                          .strip().lower() == "true"),
            )
            client = OmadaOpenApiClient(config)
        except OpenApiError as exc:
            config_error = exc.code
        except Exception:
            config_error = "openapi_configuration_invalid"
    checks: list[dict[str, object]] = []
    if config_error is not None:
        checks.append(_check("configuration", "error", config_error))
    else:
        checks.append(_check("configuration", "ok",
                             detail="Controller-Adresse und TLS-Vertrauensmodus sind gültig gesetzt."))
    checks.extend(_controller_checks(client, config_error))
    checks.append(_mcp_check(
        connector_url if connector_url is not None else
        os.getenv("OMADA_CONNECTOR_URL", "http://127.0.0.1:18080"),
        connector_token_file if connector_token_file is not None else
        os.getenv("OMADA_CONNECTOR_TOKEN_FILE"),
    ))
    status = "ok" if all(check["status"] == "ok" for check in checks) else "incomplete"
    return {"status": status, "read_only": True, "checks": checks,
            "limitations": [
                "The read-permission check covers only the site inventory; other routes can require different roles.",
                "The MCP check validates protocol steps against this connector, not a third-party agent application's configuration or compatibility.",
                "No names, addresses, credentials, access tokens, or inventory references are included.",
            ]}


def main() -> int:
    result = run_setup_check()
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
