from __future__ import annotations

import json
import hashlib
import hmac
import http.client
import itertools
import os
import re
import stat
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from .omada import OmadaClient, OmadaConfig, OmadaError
except ImportError:  # direct execution in the image
    from omada import OmadaClient, OmadaConfig, OmadaError

try:
    from .openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
except ImportError:  # direct execution in the image
    from openapi import OmadaOpenApiClient, OpenApiConfig, OpenApiError
try:
    from .changes import ChangeError, RadioChangePlans
except ImportError:  # direct execution in the image
    from changes import ChangeError, RadioChangePlans
try:
    from .dns_cache_changes import DnsCacheChangeError, DnsCacheChangePlans
except ImportError:  # direct execution in the image
    from dns_cache_changes import DnsCacheChangeError, DnsCacheChangePlans
try:
    from .ssid_changes import SsidChangeError, SsidChangePlans
except ImportError:  # direct execution in the image
    from ssid_changes import SsidChangeError, SsidChangePlans
try:
    from .gateway_ipv6_changes import GatewayIpv6ChangeError, GatewayIpv6IpPassthroughPlans
except ImportError:  # direct execution in the image
    from gateway_ipv6_changes import GatewayIpv6ChangeError, GatewayIpv6IpPassthroughPlans
try:
    from .poe_changes import PoeChangeError, PoeModePlans
except ImportError:  # direct execution in the image
    from poe_changes import PoeChangeError, PoeModePlans
try:
    from .port_status_changes import PortStatusChangeError, SwitchPortStatusPlans
except ImportError:  # direct execution in the image
    from port_status_changes import PortStatusChangeError, SwitchPortStatusPlans
try:
    from .port_name_changes import PortNameChangeError, SwitchPortNamePlans
except ImportError:  # direct execution in the image
    from port_name_changes import PortNameChangeError, SwitchPortNamePlans
try:
    from .band_steering_changes import BandSteeringChangeError, BandSteeringChangePlans
except ImportError:  # direct execution in the image
    from band_steering_changes import BandSteeringChangeError, BandSteeringChangePlans
try:
    from .rrm_mode_changes import RrmModeChangeError, RrmModePlans
except ImportError:  # direct execution in the image
    from rrm_mode_changes import RrmModeChangeError, RrmModePlans
try:
    from .site_led_changes import SiteLedChangeError, SiteLedPlans
except ImportError:  # direct execution in the image
    from site_led_changes import SiteLedChangeError, SiteLedPlans
try:
    from .controller_radius_proxy_changes import (
        ControllerRadiusProxyChangeError, ControllerRadiusProxyPlans,
    )
except ImportError:
    from controller_radius_proxy_changes import (
        ControllerRadiusProxyChangeError, ControllerRadiusProxyPlans,
    )
try:
    from .ap_afc_changes import ApAfcChangeError, ApAfcPlans
except ImportError:  # direct execution in the image
    from ap_afc_changes import ApAfcChangeError, ApAfcPlans
try:
    from .site_lldp_changes import SiteLldpChangeError, SiteLldpPlans
except ImportError:  # direct execution in the image
    from site_lldp_changes import SiteLldpChangeError, SiteLldpPlans
try:
    from .dpi_changes import SiteDpiLoggingChangeError, SiteDpiLoggingPlans
except ImportError:  # direct execution in the image
    from dpi_changes import SiteDpiLoggingChangeError, SiteDpiLoggingPlans
try:
    from .gateway_voip_changes import GatewayVoipChangeError, GatewayVoipPlans
except ImportError:  # direct execution in the image
    from gateway_voip_changes import GatewayVoipChangeError, GatewayVoipPlans
try:
    from .gateway_tag_qos_changes import GatewayTagQosChangeError, GatewayTagQosPlans
except ImportError:  # direct execution in the image
    from gateway_tag_qos_changes import GatewayTagQosChangeError, GatewayTagQosPlans
try:
    from .ap_channel_limit_changes import ApChannelLimitChangeError, ApChannelLimitPlans
except ImportError:  # direct execution in the image
    from ap_channel_limit_changes import ApChannelLimitChangeError, ApChannelLimitPlans
try:
    from .ap_ofdma_changes import ApOfdmaChangeError, ApOfdmaPlans
except ImportError:  # direct execution in the image
    from ap_ofdma_changes import ApOfdmaChangeError, ApOfdmaPlans
try:
    from .ap_qos_changes import ApQosChangeError, ApQosPlans
except ImportError:  # direct execution in the image
    from ap_qos_changes import ApQosChangeError, ApQosPlans
try:
    from .switch_cable_test_changes import SwitchCableTestError, SwitchCableTestPlans
except ImportError:  # direct execution in the image
    from switch_cable_test_changes import SwitchCableTestError, SwitchCableTestPlans
try:
    from .operation_registry import REGISTRY, RegistryError
except ImportError:  # direct execution in the image
    from operation_registry import REGISTRY, RegistryError
try:
    from .olt_onu_inventory_summary import OltOnuInventoryError, validate_pon_port_selector
except ImportError:  # direct execution in the image
    from olt_onu_inventory_summary import OltOnuInventoryError, validate_pon_port_selector
try:
    from .site_log_window_summary import SiteLogWindowError, resolve_local_site_log_window
except ImportError:  # direct execution in the image
    from site_log_window_summary import SiteLogWindowError, resolve_local_site_log_window
try:
    from .journal_runtime import JournalRuntime, initialize_journal_runtime
except ImportError:  # direct execution in the image
    from journal_runtime import JournalRuntime, initialize_journal_runtime
try:
    from .mcp import handle_mcp_request, McpRequestError
except ImportError:  # direct execution in the image
    from mcp import handle_mcp_request, McpRequestError
try:
    from .diagnostic_capability_report import project_diagnostic_capability_report
except ImportError:  # direct execution in the image
    from diagnostic_capability_report import project_diagnostic_capability_report
try:
    from .operator_approval import OperatorApprovalError, load_operator_key, verify_approval
    from .approval_plans import ApprovalPlanError, build_approval_summary
except ImportError:  # direct execution in the image
    from operator_approval import OperatorApprovalError, load_operator_key, verify_approval
    from approval_plans import ApprovalPlanError, build_approval_summary


VERSION = "0.3.0-dev"
_OPENAPI_LOCK = threading.RLock()
_OPENAPI_CLIENT: OmadaOpenApiClient | None = None
_JOURNAL_RUNTIME: JournalRuntime | None = None
_RADIO_PLANS: RadioChangePlans | None = None
_DNS_CACHE_PLANS: DnsCacheChangePlans | None = None
_SSID_PLANS: SsidChangePlans | None = None
_GATEWAY_IPV6_PLANS: GatewayIpv6IpPassthroughPlans | None = None
_POE_PLANS: PoeModePlans | None = None
_PORT_STATUS_PLANS: SwitchPortStatusPlans | None = None
_PORT_NAME_PLANS: SwitchPortNamePlans | None = None
_BAND_STEERING_PLANS: BandSteeringChangePlans | None = None
_RRM_MODE_PLANS: RrmModePlans | None = None
_SITE_LED_PLANS: SiteLedPlans | None = None
_CONTROLLER_RADIUS_PROXY_PLANS: ControllerRadiusProxyPlans | None = None
_AP_AFC_PLANS: ApAfcPlans | None = None
_SITE_LLDP_PLANS: SiteLldpPlans | None = None
_SITE_DPI_PLANS: SiteDpiLoggingPlans | None = None
_GATEWAY_VOIP_PLANS: GatewayVoipPlans | None = None
_GATEWAY_TAG_QOS_PLANS: GatewayTagQosPlans | None = None
_AP_CHANNEL_LIMIT_PLANS: ApChannelLimitPlans | None = None
_AP_OFDMA_PLANS: ApOfdmaPlans | None = None
_AP_QOS_PLANS: ApQosPlans | None = None
_SWITCH_CABLE_TEST_PLANS: SwitchCableTestPlans | None = None
_CONSUMED_APPROVALS: dict[str, int] = {}
_ACTIVE_APPROVAL: dict[str, object] | None = None
_MAX_CONSUMED_APPROVALS = 2048
_CHANGE_PLAN_KINDS = frozenset({"radio", "dns-cache", "ssid", "gateway-ipv6", "poe", "switch-port-status", "switch-port-name", "band-steering", "rrm-mode", "site-led", "ap-afc", "site-lldp", "ap-channel-limit", "ap-ofdma", "ap-qos", "site-dpi", "gateway-voip", "gateway-tag-qos", "switch-cable-test", "switch-cable-test-cancel", "controller-radius-proxy"})
_MAX_HTTP_RESPONSE_BYTES = 1_048_576
_MAX_REQUEST_BYTES = 4096


def _safe_upstream_error(status: int, raw: bytes) -> tuple[str, int | None, int | None]:
    """Read only stable codes and numeric upstream status fields from an error body."""
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        value = None
    if not isinstance(value, dict):
        return "connector_http_error", None, None
    code = value.get("error")
    if not isinstance(code, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code) is None:
        code = "connector_http_error"
    http_status = value.get("upstream_http_status")
    if type(http_status) is not int or not 100 <= http_status <= 599:
        http_status = None
    api_code = value.get("upstream_error_code")
    if type(api_code) is not int or not -(2**31) <= api_code <= 2**31 - 1:
        api_code = None
    if status < 400:
        return "connector_http_error", None, None
    return code, http_status, api_code
_AP_PARTS = {
    "radio-config": "radio_config",
    "radios": "radios",
    "scan-status": "scan_status",
    "channel-load": "channel_load",
}


def _writes_enabled() -> bool:
    """Return the current process-local opt-in state (never a cached value)."""
    return os.getenv("OMADA_ENABLE_WRITES", "").strip().lower() == "true"


def _journal_runtime(client: OmadaOpenApiClient | None = None) -> JournalRuntime:
    """Initialize at most once, while the caller holds the shared RLock."""
    global _JOURNAL_RUNTIME
    if _JOURNAL_RUNTIME is None:
        directory = os.getenv("OMADA_CHANGE_JOURNAL_DIR")
        if not directory:
            _JOURNAL_RUNTIME = JournalRuntime("unconfigured")
        else:
            try:
                client = client or _openapi_client()
                config = client.config
                _JOURNAL_RUNTIME = initialize_journal_runtime(
                    directory,
                    reference_key=client._ref_key,
                    reference_key_persistent=bool(config.reference_key_file),
                    controller_url=config.base_url,
                    controller_id=config.controller_id,
                )
            except Exception:
                # Keep the HTTP surface limited to fixed, non-sensitive codes.
                _JOURNAL_RUNTIME = JournalRuntime("unavailable", error_code="journal_unavailable")
    return _JOURNAL_RUNTIME


def _operator_key(client: OmadaOpenApiClient | None = None) -> bytes:
    path = os.getenv("OMADA_OPERATOR_APPROVAL_KEY_FILE", "")
    if not path:
        raise OperatorApprovalError("operator_key_unavailable")
    key = load_operator_key(path)
    client = client or _openapi_client()
    reference_key = getattr(client, "_ref_key", None)
    if not isinstance(reference_key, bytes) or len(reference_key) != 32:
        raise OperatorApprovalError("operator_key_unavailable")
    caller_key = _caller_token()
    if hmac.compare_digest(key, reference_key) or (caller_key is not None and hmac.compare_digest(key, caller_key)):
        raise OperatorApprovalError("operator_key_not_separate")
    return key


def _effective_writes(client: OmadaOpenApiClient | None = None) -> bool:
    if not _writes_enabled():
        return False
    with _OPENAPI_LOCK:
        if not _journal_runtime(client).ready:
            return False
        try:
            _operator_key(client)
        except (OperatorApprovalError, OpenApiError):
            return False
        return True


def _approve_apply(client: OmadaOpenApiClient, plans: object, kind: str,
                   plan_id: str, body: dict[str, object]) -> None:
    global _ACTIVE_APPROVAL
    if set(body) != {"approval"} or not isinstance(body["approval"], dict):
        raise OperatorApprovalError("operator_approval_required")
    summary = build_approval_summary(kind, plan_id, plans)
    key = _operator_key(client)
    approval = body["approval"]
    verify_approval(key, approval, operation=kind, plan_id=plan_id,
                    plan_digest=summary["digest"])
    now = int(time.time())
    for nonce, expiry in list(_CONSUMED_APPROVALS.items()):
        if expiry <= now:
            del _CONSUMED_APPROVALS[nonce]
    nonce = approval["nonce"]
    if nonce in _CONSUMED_APPROVALS:
        raise OperatorApprovalError("operator_approval_reused")
    if len(_CONSUMED_APPROVALS) >= _MAX_CONSUMED_APPROVALS:
        raise OperatorApprovalError("operator_approval_capacity_reached")
    _CONSUMED_APPROVALS[nonce] = approval["expires_at"]
    _ACTIVE_APPROVAL = {"kind": kind, "expires_at": approval["expires_at"],
                        "key_digest": hashlib.sha256(key).digest(), "client": client}


def _ensure_current_approval(kind: str) -> None:
    active = _ACTIVE_APPROVAL
    if (not isinstance(active, dict) or active.get("kind") != kind or
            type(active.get("expires_at")) is not int or int(time.time()) >= active["expires_at"]):
        raise OperatorApprovalError("operator_approval_expired")
    expected = active.get("key_digest")
    if not isinstance(expected, bytes) or len(expected) != 32:
        raise OperatorApprovalError("operator_approval_unavailable")
    current_key = _operator_key(active.get("client"))
    if not hmac.compare_digest(hashlib.sha256(current_key).digest(), expected):
        raise OperatorApprovalError("operator_approval_revoked")


def _guarded_dispatch(kind: str, callback, *args):
    _ensure_current_approval(kind)
    owner = getattr(callback, "__self__", None)
    if owner is None or getattr(owner, "_write_dispatch_guard", None) is not None:
        raise OperatorApprovalError("operator_approval_unavailable")
    dispatch_thread = threading.get_ident()
    used = False
    def dispatch_guard():
        nonlocal used
        if used or threading.get_ident() != dispatch_thread:
            raise OperatorApprovalError("operator_approval_unavailable")
        _ensure_current_approval(kind)
        used = True
    owner._write_dispatch_guard = dispatch_guard
    try:
        return callback(*args)
    finally:
        owner._write_dispatch_guard = None


def _apply_with_operator_approval(client: OmadaOpenApiClient, plans: object, kind: str,
                                  plan_id: str, body: dict[str, object]):
    global _ACTIVE_APPROVAL
    if not plans.writes_enabled:
        return (plans.apply_cancel(plan_id) if kind == "switch-cable-test-cancel"
                else plans.apply(plan_id))
    _approve_apply(client, plans, kind, plan_id, body)
    try:
        return (plans.apply_cancel(plan_id) if kind == "switch-cable-test-cancel"
                else plans.apply(plan_id))
    finally:
        _ACTIVE_APPROVAL = None


def _journal_http_failure() -> dict[str, object]:
    runtime = _journal_runtime()
    return {"status": "error", "error": runtime.error_code or "journal_unavailable"}


def _read_change_journal_summary() -> dict[str, object]:
    """Summarize only the already-open, controller-bound local journal."""
    runtime = _JOURNAL_RUNTIME
    if runtime is None:
        return {"status": "unavailable", "error": "journal_not_open"}
    if runtime.status == "unconfigured":
        return {"status": "unavailable", "error": "journal_unconfigured"}
    if not runtime.ready:
        return {"status": "unavailable", "error": runtime.error_code or "journal_unavailable"}
    try:
        return runtime.journal.summary()
    except ChangeJournalError as exc:
        return {"status": "unavailable", "error": exc.code}


def _caller_token() -> bytes | None:
    """Read the configured bearer token; missing or invalid config disables routes."""
    path = os.getenv("OMADA_CONNECTOR_TOKEN_FILE", "").strip()
    if not path:
        return None
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
             getattr(os, "O_NONBLOCK", 0))
    try:
        fd = os.open(path, flags)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
                return None
            value = os.read(fd, 4097).strip()
        finally:
            os.close(fd)
    except (OSError, ValueError):
        return None
    if (len(value) < 32 or len(value) > 4096 or
            any(byte < 0x21 or byte > 0x7e for byte in value)):
        return None
    return value


def _openapi_client() -> OmadaOpenApiClient:
    global _OPENAPI_CLIENT
    if _OPENAPI_CLIENT is None:
        _OPENAPI_CLIENT = OmadaOpenApiClient(OpenApiConfig.from_env())
    return _OPENAPI_CLIENT


def _radio_plans(client: OmadaOpenApiClient) -> RadioChangePlans:
    global _RADIO_PLANS
    if _RADIO_PLANS is None:
        def read(site_ref: str, device_ref: str):
            return client.read_ap_radio_part(site_ref, device_ref, "radio_config")["data"]
        def write(site_ref: str, device_ref: str, changes: dict[str, object]):
            if all(set(fields) == {"txPowerLevel"} for fields in changes.values()):
                return _guarded_dispatch("radio", client.patch_ap_radio_power, site_ref, device_ref, changes)
            return _guarded_dispatch("radio", client.patch_ap_radio_config, site_ref, device_ref, changes)
        def catalog(site_ref: str, device_ref: str):
            radios = client.read_ap_available_channels(site_ref, device_ref)["data"]["radios"]
            result = {}
            for radio in radios:
                field = {0: "radioSetting2g", 3: "radioSetting6g"}.get(radio["radio_id"])
                if field:
                    result[field] = [{"index": channel["channel_index"], "freq": channel["frequency_mhz"],
                                      "available_widths_mhz": channel["available_widths_mhz"]}
                                     for channel in radio["channels"]]
            return result
        runtime = _journal_runtime(client)
        _RADIO_PLANS = RadioChangePlans(read, write,
            catalog=catalog,
            writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None,
            require_journal=True)
    return _RADIO_PLANS


def _dns_cache_plans(client: OmadaOpenApiClient) -> DnsCacheChangePlans:
    global _DNS_CACHE_PLANS
    if _DNS_CACHE_PLANS is None:
        runtime = _journal_runtime(client)
        _DNS_CACHE_PLANS = DnsCacheChangePlans(
            client.read_dns_cache_change_state,
            lambda site_ref, changes: _guarded_dispatch("dns-cache", client.put_dns_cache_settings, site_ref, changes),
            writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None,
            require_journal=True,
        )
    return _DNS_CACHE_PLANS


def _ssid_plans(client: OmadaOpenApiClient) -> SsidChangePlans:
    global _SSID_PLANS
    if _SSID_PLANS is None:
        runtime = _journal_runtime(client)
        _SSID_PLANS = SsidChangePlans(
            client.read_ssid_enable_state,
            lambda site_ref, ssid_ref, changes: _guarded_dispatch("ssid", client.patch_ssid_enable, site_ref, ssid_ref, changes),
            writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None,
            require_journal=True,
        )
    return _SSID_PLANS


def _gateway_ipv6_plans(client: OmadaOpenApiClient) -> GatewayIpv6IpPassthroughPlans:
    global _GATEWAY_IPV6_PLANS
    if _GATEWAY_IPV6_PLANS is None:
        runtime = _journal_runtime(client)
        def read(site_ref: str, gateway_ref: str):
            return client.read_gateway_ipv6_ip_passthrough(site_ref, gateway_ref)["data"]
        def write(site_ref: str, gateway_ref: str, change: dict[str, bool]):
            return _guarded_dispatch("gateway-ipv6", client.patch_gateway_ipv6_ip_passthrough, site_ref, gateway_ref, change)
        _GATEWAY_IPV6_PLANS = GatewayIpv6IpPassthroughPlans(
            read, write, writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None,
            require_journal=True)
    return _GATEWAY_IPV6_PLANS


def _poe_plans(client: OmadaOpenApiClient) -> PoeModePlans:
    global _POE_PLANS
    if _POE_PLANS is None:
        runtime = _journal_runtime(client)
        def read(site_ref: str, switch_ref: str, port: int):
            try:
                return client.read_switch_port_poe_state(site_ref, switch_ref, port)["data"]
            except OpenApiError as exc:
                safe_codes = {
                    "site_ref_invalid", "site_ref_unknown", "switch_ref_invalid",
                    "switch_ref_unknown", "switch_port_invalid", "switch_port_unknown",
                    "switch_port_ambiguous", "poe_mode_invalid", "poe_unsupported",
                    "profile_override_required", "openapi_response_invalid",
                }
                if exc.code in safe_codes:
                    raise PoeChangeError(exc.code) from None
                raise
        def write(site_ref: str, switch_ref: str, port: int, body: dict[str, int]):
            return _guarded_dispatch("poe", client.put_switch_port_poe_mode, site_ref, switch_ref, port, body)
        _POE_PLANS = PoeModePlans(read, write,
            writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None,
            require_journal=True)
    return _POE_PLANS


def _port_status_plans(client: OmadaOpenApiClient) -> SwitchPortStatusPlans:
    global _PORT_STATUS_PLANS
    if _PORT_STATUS_PLANS is None:
        runtime = _journal_runtime(client)
        def read(site_ref: str, switch_ref: str, port: int):
            return client.read_switch_port_status(site_ref, switch_ref, port)["data"]
        def write(site_ref: str, switch_ref: str, port: int, body: dict[str, int]):
            return _guarded_dispatch("switch-port-status", client.put_switch_port_status, site_ref, switch_ref, port, body)
        _PORT_STATUS_PLANS = SwitchPortStatusPlans(
            read, write, writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None, require_journal=True)
    return _PORT_STATUS_PLANS


def _port_name_plans(client: OmadaOpenApiClient) -> SwitchPortNamePlans:
    global _PORT_NAME_PLANS
    if _PORT_NAME_PLANS is None:
        runtime = _journal_runtime(client)
        def read(site_ref: str, switch_ref: str, port: int):
            try:
                return client.read_switch_port_name(site_ref, switch_ref, port)["data"]
            except OpenApiError as exc:
                safe_codes = {
                    "site_ref_invalid", "site_ref_unknown", "switch_ref_invalid",
                    "switch_ref_unknown", "switch_ref_ambiguous", "switch_port_invalid",
                    "switch_port_unknown", "switch_port_ambiguous", "openapi_response_invalid",
                }
                if exc.code in safe_codes:
                    raise PortNameChangeError(exc.code) from None
                raise
        def write(site_ref: str, switch_ref: str, port: int, body: dict[str, str]):
            return _guarded_dispatch("switch-port-name", client.put_switch_port_name,
                                     site_ref, switch_ref, port, body)
        _PORT_NAME_PLANS = SwitchPortNamePlans(
            read, write, writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None, require_journal=True)
    return _PORT_NAME_PLANS


def _band_steering_plans(client: OmadaOpenApiClient) -> BandSteeringChangePlans:
    global _BAND_STEERING_PLANS
    if _BAND_STEERING_PLANS is None:
        runtime = _journal_runtime(client)
        def read(site_ref: str):
            return client.read_band_steering(site_ref)["data"]
        def write(site_ref: str, body: dict[str, int]):
            return _guarded_dispatch("band-steering", client.patch_band_steering, site_ref, body)
        _BAND_STEERING_PLANS = BandSteeringChangePlans(
            read, write, writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None, require_journal=True)
    return _BAND_STEERING_PLANS


def _rrm_mode_plans(client: OmadaOpenApiClient) -> RrmModePlans:
    global _RRM_MODE_PLANS
    if _RRM_MODE_PLANS is None:
        runtime = _journal_runtime(client)
        def read(site_ref: str):
            try:
                return client.read_rrm_change_state(site_ref)["data"]
            except OpenApiError as exc:
                if exc.code == "rrm_change_state_unavailable":
                    raise RrmModeChangeError("rrm_state_unsupported") from None
                raise
        def write(site_ref: str, body: dict[str, object]):
            return _guarded_dispatch("rrm-mode", client.put_rrm_mode, site_ref, body)
        _RRM_MODE_PLANS = RrmModePlans(
            read, write, writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None, require_journal=True)
    return _RRM_MODE_PLANS


def _site_led_plans(client: OmadaOpenApiClient) -> SiteLedPlans:
    global _SITE_LED_PLANS
    if _SITE_LED_PLANS is None:
        runtime = _journal_runtime(client)
        def read(site_ref: str):
            return client.read_site_led(site_ref)["data"]
        def write(site_ref: str, body: dict[str, bool]):
            return _guarded_dispatch("site-led", client.put_site_led, site_ref, body)
        _SITE_LED_PLANS = SiteLedPlans(
            read, write, writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None, require_journal=True)
    return _SITE_LED_PLANS


def _controller_radius_proxy_plans(client: OmadaOpenApiClient) -> ControllerRadiusProxyPlans:
    global _CONTROLLER_RADIUS_PROXY_PLANS
    if _CONTROLLER_RADIUS_PROXY_PLANS is None:
        runtime = _journal_runtime(client)
        def read():
            result = client.read_controller_radius_proxy()
            data = result.get("data")
            settings = data.get("settings") if isinstance(data, dict) else None
            if (result.get("partial") is not False or not isinstance(data, dict) or
                    data.get("missing_required_count") != 0 or data.get("invalid_count") != 0 or
                    data.get("unknown_field_count") != 0 or not isinstance(settings, dict) or
                    "enabled" not in settings or "port" not in settings):
                raise ControllerRadiusProxyChangeError("state_unavailable")
            optional = {"requireMessageAuthenticator": settings.get("require_message_authenticator"),
                        "limitProxyState": settings.get("limit_proxy_state")}
            return {"enable": settings["enabled"], "port": settings["port"], **optional}
        def write(body: dict[str, object]):
            return _guarded_dispatch("controller-radius-proxy",
                                     client.patch_controller_radius_proxy, body)
        _CONTROLLER_RADIUS_PROXY_PLANS = ControllerRadiusProxyPlans(
            read, write, writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None, require_journal=True)
    return _CONTROLLER_RADIUS_PROXY_PLANS


def _ap_afc_plans(client: OmadaOpenApiClient) -> ApAfcPlans:
    global _AP_AFC_PLANS
    if _AP_AFC_PLANS is None:
        runtime = _journal_runtime(client)
        def read(site_ref: str, device_ref: str):
            return client.read_ap_afc(site_ref, device_ref)["data"]
        def write(site_ref: str, device_ref: str, body: dict[str, bool]):
            return _guarded_dispatch("ap-afc", client.put_ap_afc, site_ref, device_ref, body)
        _AP_AFC_PLANS = ApAfcPlans(
            read, write, writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None, require_journal=True)
    return _AP_AFC_PLANS


def _site_lldp_plans(client: OmadaOpenApiClient) -> SiteLldpPlans:
    global _SITE_LLDP_PLANS
    if _SITE_LLDP_PLANS is None:
        runtime = _journal_runtime(client)
        def read(site_ref: str):
            return client.read_site_lldp(site_ref)["data"]
        def write(site_ref: str, body: dict[str, bool]):
            return _guarded_dispatch("site-lldp", client.patch_site_lldp, site_ref, body)
        _SITE_LLDP_PLANS = SiteLldpPlans(
            read, write, writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None, require_journal=True)
    return _SITE_LLDP_PLANS


def _site_dpi_plans(client: OmadaOpenApiClient) -> SiteDpiLoggingPlans:
    global _SITE_DPI_PLANS
    if _SITE_DPI_PLANS is None:
        runtime = _journal_runtime(client)
        def read(site_ref: str):
            return client.read_site_dpi_logging(site_ref)["data"]
        def write(site_ref: str, state: dict[str, bool]):
            return _guarded_dispatch("site-dpi", client.put_site_dpi_logging, site_ref, state)
        _SITE_DPI_PLANS = SiteDpiLoggingPlans(
            read, write, writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None, require_journal=True)
    return _SITE_DPI_PLANS


def _gateway_voip_plans(client: OmadaOpenApiClient) -> GatewayVoipPlans:
    global _GATEWAY_VOIP_PLANS
    if _GATEWAY_VOIP_PLANS is None:
        runtime = _journal_runtime(client)
        def read(site_ref: str):
            return client.read_gateway_voip(site_ref)["data"]
        def write(site_ref: str, full_state: dict[str, object]):
            return _guarded_dispatch("gateway-voip", client.put_gateway_voip,
                                     site_ref, full_state)
        _GATEWAY_VOIP_PLANS = GatewayVoipPlans(
            read, write, writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None, require_journal=True)
    return _GATEWAY_VOIP_PLANS


def _gateway_tag_qos_plans(client: OmadaOpenApiClient) -> GatewayTagQosPlans:
    global _GATEWAY_TAG_QOS_PLANS
    if _GATEWAY_TAG_QOS_PLANS is None:
        runtime = _journal_runtime(client)
        def read(site_ref: str):
            return client.read_gateway_tag_qos(site_ref)["data"]
        def write(site_ref: str, full_state: dict[str, object]):
            return _guarded_dispatch("gateway-tag-qos", client.put_gateway_tag_qos,
                                     site_ref, full_state)
        _GATEWAY_TAG_QOS_PLANS = GatewayTagQosPlans(
            read, write, writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None, require_journal=True)
    return _GATEWAY_TAG_QOS_PLANS


def _ap_channel_limit_plans(client: OmadaOpenApiClient) -> ApChannelLimitPlans:
    global _AP_CHANNEL_LIMIT_PLANS
    if _AP_CHANNEL_LIMIT_PLANS is None:
        runtime = _journal_runtime(client)
        def read(site_ref: str, device_ref: str):
            return client.read_ap_channel_limit_change_state(site_ref, device_ref)["data"]
        def write(site_ref: str, device_ref: str, body: dict[str, int]):
            return _guarded_dispatch("ap-channel-limit", client.put_ap_channel_limit,
                                     site_ref, device_ref, body)
        _AP_CHANNEL_LIMIT_PLANS = ApChannelLimitPlans(
            read, write, writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None, require_journal=True)
    return _AP_CHANNEL_LIMIT_PLANS


def _ap_ofdma_plans(client: OmadaOpenApiClient) -> ApOfdmaPlans:
    global _AP_OFDMA_PLANS
    if _AP_OFDMA_PLANS is None:
        runtime = _journal_runtime(client)
        def read(site_ref: str, device_ref: str):
            return client.read_ap_ofdma_change_state(site_ref, device_ref)["data"]
        def write(site_ref: str, device_ref: str, patch: dict[str, bool]):
            return _guarded_dispatch("ap-ofdma", client.patch_ap_ofdma,
                                     site_ref, device_ref, patch)
        _AP_OFDMA_PLANS = ApOfdmaPlans(
            read, write, writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None, require_journal=True)
    return _AP_OFDMA_PLANS


def _ap_qos_plans(client: OmadaOpenApiClient) -> ApQosPlans:
    global _AP_QOS_PLANS
    if _AP_QOS_PLANS is None:
        runtime = _journal_runtime(client)
        def read(site_ref: str, device_ref: str):
            return client.read_ap_qos_change_state(site_ref, device_ref)["data"]
        def write(site_ref: str, device_ref: str, body: dict[str, bool]):
            return _guarded_dispatch("ap-qos", client.patch_ap_qos,
                                     site_ref, device_ref, body)
        _AP_QOS_PLANS = ApQosPlans(
            read, write, writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None, require_journal=True)
    return _AP_QOS_PLANS


def _switch_cable_test_plans(client: OmadaOpenApiClient) -> SwitchCableTestPlans:
    global _SWITCH_CABLE_TEST_PLANS
    if _SWITCH_CABLE_TEST_PLANS is None:
        runtime = _journal_runtime(client)
        def start(site_ref: str, switch_ref: str, ports: list[int]):
            return _guarded_dispatch("switch-cable-test", client.start_switch_cable_test,
                                     site_ref, switch_ref, ports)
        def cancel(site_ref: str, switch_ref: str):
            return _guarded_dispatch("switch-cable-test-cancel", client.cancel_switch_cable_test,
                                     site_ref, switch_ref)
        _SWITCH_CABLE_TEST_PLANS = SwitchCableTestPlans(
            read_ports=client.read_switch_cable_test_ports,
            read_logs=client.read_switch_cable_test_logs,
            read_results=client.read_switch_cable_test_full_results,
            start=start, cancel=cancel,
            writes_enabled=_writes_enabled() and runtime.ready,
            journal=runtime.journal if runtime.ready else None, require_journal=True)
    return _SWITCH_CABLE_TEST_PLANS


def _in_doubt_manager(kind: str):
    client = _openapi_client()
    _journal_runtime(client)
    if kind == "radio":
        return _radio_plans(client), ChangeError
    if kind == "dns-cache":
        return _dns_cache_plans(client), DnsCacheChangeError
    if kind == "ssid":
        return _ssid_plans(client), SsidChangeError
    if kind == "gateway-ipv6":
        return _gateway_ipv6_plans(client), GatewayIpv6ChangeError
    if kind == "poe":
        return _poe_plans(client), PoeChangeError
    if kind == "switch-port-status":
        return _port_status_plans(client), PortStatusChangeError
    if kind == "switch-port-name":
        return _port_name_plans(client), PortNameChangeError
    if kind == "band-steering":
        return _band_steering_plans(client), BandSteeringChangeError
    if kind == "rrm-mode":
        return _rrm_mode_plans(client), RrmModeChangeError
    if kind == "site-led":
        return _site_led_plans(client), SiteLedChangeError
    if kind == "controller-radius-proxy":
        return _controller_radius_proxy_plans(client), ControllerRadiusProxyChangeError
    if kind == "ap-afc":
        return _ap_afc_plans(client), ApAfcChangeError
    if kind == "site-lldp":
        return _site_lldp_plans(client), SiteLldpChangeError
    if kind == "site-dpi":
        return _site_dpi_plans(client), SiteDpiLoggingChangeError
    if kind == "gateway-voip":
        return _gateway_voip_plans(client), GatewayVoipChangeError
    if kind == "gateway-tag-qos":
        return _gateway_tag_qos_plans(client), GatewayTagQosChangeError
    if kind == "ap-channel-limit":
        return _ap_channel_limit_plans(client), ApChannelLimitChangeError
    if kind == "ap-ofdma":
        return _ap_ofdma_plans(client), ApOfdmaChangeError
    if kind == "ap-qos":
        return _ap_qos_plans(client), ApQosChangeError
    if kind in {"switch-cable-test", "switch-cable-test-cancel"}:
        return _switch_cable_test_plans(client), SwitchCableTestError
    raise ValueError("change_plan_kind_invalid")


def _in_doubt_status(code: str) -> HTTPStatus:
    if code.startswith("journal_"):
        return HTTPStatus.SERVICE_UNAVAILABLE
    if code == "plan_unknown":
        return HTTPStatus.NOT_FOUND
    if code in {"plan_not_in_doubt", "operator_confirmation_required", "plan_already_consumed", "cable_test_not_cancellable"}:
        return HTTPStatus.CONFLICT
    return HTTPStatus.BAD_REQUEST


class Handler(BaseHTTPRequestHandler):
    server_version = "omada-universal-connector/" + VERSION

    def _send(self, status: int, body: dict[str, object]) -> None:
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(encoded) > _MAX_HTTP_RESPONSE_BYTES:
            status = HTTPStatus.BAD_GATEWAY
            encoded = b'{"error":"response_too_large","status":"error"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/change-journal/summary":
            if not self._authorized():
                return
            with _OPENAPI_LOCK:
                result = _read_change_journal_summary()
            status = HTTPStatus.OK if result.get("status") == "ok" else HTTPStatus.SERVICE_UNAVAILABLE
            self._send(status, result)
            return
        ssid_network_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/ssid-network-summary", self.path)
        if ssid_network_match:
            if not self._authorized():
                return
            result = self._mcp_ssid_network_summary({"site_ref": ssid_network_match.group(1)})
            status = HTTPStatus.OK if result.get("status") == "ok" else HTTPStatus.BAD_GATEWAY
            self._send(status, result)
            return
        if self.path == "/healthz":
            self._send(HTTPStatus.OK, {"status": "ok"})
            return
        if self.path == "/state":
            try:
                with _OPENAPI_LOCK:
                    client = _OPENAPI_CLIENT
                    runtime = _journal_runtime(client)
                    approval_status = "unconfigured" if not os.getenv("OMADA_OPERATOR_APPROVAL_KEY_FILE") else "unavailable"
                    if runtime.ready:
                        try:
                            _operator_key(client)
                            approval_status = "ready"
                        except (OperatorApprovalError, OpenApiError):
                            pass
                    effective_writes = _writes_enabled() and runtime.ready and approval_status == "ready"
            except Exception:
                runtime = JournalRuntime("unavailable", error_code="journal_unavailable")
                effective_writes = False
                approval_status = "unavailable"
            self._send(HTTPStatus.OK, {
                "service": "omada-universal-connector",
                "version": VERSION,
                "status": "ready",
                "mode": os.getenv("OMADA_MODE", "live"),
                "read_only": not effective_writes,
                "journal_status": "unavailable" if runtime.status == "ready" and not runtime.ready else runtime.status,
                "journal_error": (runtime.error_code or "journal_unavailable") if runtime.status == "ready" and not runtime.ready else runtime.error_code,
                "approval_status": approval_status,
                "implemented_resources": ['site_gateway_isp_summary', 'site_top_ap_retry_drop_summary', 'site_active_ap_summary', 'site_active_ap_v2_summary', 'site_hotspot_statistics_summary', 'site_allowed_application_summary', 'site_blocked_application_summary', 'site_dashboard_all_tabs_summary', 'site_dashboard_non_overall_tabs_summary', 'site_specific_app_traffic_summary', 'site_specific_client_traffic_summary', 'site_application_traffic_summary', 'site_wan_lan_status_summary', 'site_arp_detect_status_summary', 'site_disaster_mode_status', 'site_specification_summary', 'site_portal_logout_domain', 'site_wids_config', 'site_wips_config', 'site_acl_config_mode', 'site_attack_defense_summary', 'site_attack_defense_defaults_summary', 'site_alg_config', 'site_firewall_settings', 'site_firewall_defaults', 'site_bandwidth_control', 'site_wan_ports_summary', 'site_wan_port_availability_summary', 'site_virtual_wan_summary', 'site_wan_max_speed_summary', 'gateway_info_summary', 'site_gateway_sim_sms_support_summary', 'site_ipsec_failover_summary', 'site_static_route_summary', 'site_nat_exception_summary', 'site_static_route_interface_options_summary', 'site_policy_route_summary', 'site_ipsec_sa_summary', 'site_ids_ips_config_summary', 'site_remote_access_tunnel_status_summary', 'site_vpn_server_config_summary', 'site_vpn_client_config_summary', 'site_vpn_server_status_summary', 'site_wan_qos_summary', 'site_upnp_template_comparison', 'site_bridge_device_summary', 'site_vlan_network_summary', 'site_lan_network_config_summary', 'site_lan_network_inventory', 'site_lan_client_inventory_summary', 'site_topology_root_candidates_summary', 'site_topology_snapshot_summary', 'site_gateway_qos_service_profiles_summary', 'site_isolated_preconfig_summary', 'site_vlan_topology_summary', 'site_vlan_topology_reference_count', 'site_es_network_overview_summary', 'site_port_schedule_ports_summary', 'site_internet_load_balance_summary', 'site_internet_basic_port_summary', 'site_wlan_group_summary', 'site_wlan_group_ssids_summary', 'site_wlan_group_ssid_config_summary', 'site_internet_summary', 'site_lte_wan_config_summary', 'site_vpn_session_summary', 'site_dhcp_candidate_summary', 'site_network_reservation_summary', 'site_dhcp_reservation_summary', 'site_dhcp_snooping_status', 'site_dhcp_snoops_summary', 'site_mdns_rule_summary', 'site_ddns_summary', 'site_snmp_settings_summary', 'site_active_switch_summary', 'site_device_memory_summary', 'site_switch_dashboard_summary', 'site_ap_interference_summary', 'site_application_category_summary', 'site_category_application_summary', 'site_category_client_summary', 'site_active_application_summary', 'site_active_client_summary', 'site_recent_clients_summary', 'site_ssid_client_count_summary', 'site_ssid_topology_device_summary', 'site_ssid_topology_reference_count', 'site_ap_topology_clients_summary', 'site_network_delivery_summary', 'site_lan_port_profiles_summary', 'site_lan_switch_profile_assignments_summary', 'site_lan_multicast_summary', 'site_bandwidth_rules_summary', 'site_log_notification_summary', 'site_lan_network_interface_summary', 'site_vpn_client_status_summary', 'site_vpn_s2s_status_summary', 'site_s2s_vpn_inventory_summary', 'site_s2s_vpn_v2_summary', 'site_s2s_peer_status_summary', 'site_remote_logging_summary', 'controller_upgrade_log_summary', 'controller_upgrade_log_inventory', 'controller_upgrade_failed_devices_summary', 'controller_upgrade_plans_summary', 'site_cpu_usage_summary', 'site_client_bubble_summary', 'site_traffic_activity_summary', 'site_isp_load_summary', 'site_vpn_tunnel_summary', 'site_open_vpn_tunnel_summary', 'site_client_activity_summary', 'site_client_association_activity_summary', 'site_client_traffic_summary', 'site_current_client_summary', 'site_past_client_summary', 'site_device_traffic_summary', 'site_client_frequency_distribution_summary', 'site_client_attachment_distribution_summary', 'site_ap_rssi_density_summary', 'site_client_rssi_distribution_summary', 'site_network_activity_summary', 'site_client_association_time_summary', 'site_ipsec_tunnel_summary', 'site_device_counts_summary', 'site_poe_usage_summary', 'site_poe_schedule_summary', 'site_port_schedule_summary', 'site_routing_table_summary', 'site_client_connection_summary', 'site_remember_setting_summary', 'site_iot_transmit_power_summary', 'site_beacon_control_summary', 'site_multicast_rate_limit_summary', 'site_mesh_summary', 'site_iot_radio_summary', 'site_iot_aging_time', 'controller_info', 'controller_health', 'controller_global_log_notification_summary', 'controller_upgrade_model_list_summary', 'controller_threat_severity_summary', 'controller_scenarios', 'controller_scenario_differences', 'controller_gateway_wan_status_summary', 'ap_overview', 'controller_client_recognition', 'controller_device_statistics', 'controller_client_active_timeout', 'controller_client_history_retention', 'controller_audit_notification', 'controller_ui_interface', 'controller_retention', 'controller_dst_info', 'controller_experience_improvement', 'controller_client_detail_info', 'controller_general_settings', 'controller_device_access', 'controller_backup_schedule', 'controller_cloud_access', 'controller_device_management', 'controller_remote_binding', 'controller_backup_result', 'controller_restore_result', 'controller_privacy_policy', 'controller_mail_status', 'controller_global_mfa_status', 'msp_cloud_access_status', 'msp_privacy_policy', 'msp_client_detail_info', 'msp_audit_notification', 'msp_device_link_topology', 'msp_device_tags', 'msp_mfa_status', 'msp_license_auto_active', 'msp_customer_roles', 'msp_dst_info', 'msp_remote_logging', 'msp_mail_server', 'msp_general_settings', 'msp_log_notification_settings', 'msp_data_retention', 'msp_ui_interface', 'msp_user_interface', 'msp_available_roles', 'msp_available_customer_roles', 'msp_dashboard_overall', 'msp_cluster_nodes', 'msp_adopt_tip', 'msp_role_summary', 'controller_remote_logging', 'controller_remote_logging_tip', 'controller_radius_proxy', 'controller_radius_server', 'controller_upgrade_port', 'controller_portal_port_settings', 'controller_port_settings', 'site_radius_user_summary', 'site_entity_summary', 'site_switch_qos_mode', 'site_switch_qos_scheduler_summary', 'site_switch_qos_dscp_summary', 'site_switch_qos_summary', 'site_switch_ddm_summary', 'site_upnp_summary', 'site_gre_tunnel_summary', 'site_ssl_vpn_summary', 'site_ssh_summary', 'site_templates', 'site_template_igmp_summary', 'site_template_upnp_summary', 'site_mld_summary', 'site_igmp_summary', 'site_iptv_summary', 'site_device_tag_summary', 'sites', 'site_overview', 'site_topology', 'site_reboot_schedule_summary', 'site_health_timeline', 'site_longest_client_uptime_summary', 'site_mac_auth_ssid_inventory', 'site_client_health_timeline', 'site_wifi_summary', 'site_6ghz_ap_presence', 'site_setting_existence', 'site_capabilities', 'site_duplicate_ssid_summary', 'ssid_ap_groups', 'site_topology_network_summary', 'site_topology_vlan_summary', 'site_unresolved_incident_count', 'site_incident_overview', 'site_incident_distribution', 'site_incident_category_counts', 'site_incident_list', 'site_batch_interference_history', 'device_health_incidents', 'client_health_incidents', 'site_incident_detail', 'site_incident_notification', 'site_anomaly_event_settings', 'site_incident_influencing_clients', 'site_incident_influencing_devices', 'site_wlan_group_capacity', 'site_ap_group_capacity', 'site_ap_group_summary', 'site_ap_group_assignment_summary', 'site_ap_group_info_summary', 'site_ap_oui_vlan_rules_summary', 'site_vlan_port_support_summary', 'site_vlan_affected_ports_summary', 'site_eap_dot1x_candidates_summary', 'site_switch_dot1x_candidates_summary', 'site_switch_support', 'experience_index', 'rf_planning_result', 'rf_planning_dashboard', 'rf_planning_dashboard_current', 'rf_planning_dashboard_history', 'rf_planning_detail', 'rf_planning_history', 'rf_planning_history_detail', 'rf_planning_recent_history', 'rf_excluded_aps', 'wifi_health', 'wifi_subhealth', 'site_dashboard_channels', 'site_client_signal_distribution', 'band_steering', 'rrm_settings', 'rrm_incompatible', 'roaming_settings', 'site_led', 'site_lldp', 'site_dpi_logging', 'gateway_voip', 'gateway_tag_qos', 'site_channel_limit', 'site_speed_test_settings', 'ap_uplink_config', 'ap_lldp_config', 'ap_port_vlans', 'ap_bridge_config', 'ap_mesh_candidates', 'ap_general_config', 'ap_ip_setting', 'ap_ipv6_setting', 'ap_p2p_info', 'ap_l3_access', 'ap_paring_window', 'ap_lag_config', 'ap_rf_scan_v2', 'ap_management_ssid', 'ap_channel_limit', 'ap_ofdma', 'ap_qos', 'ap_lag', 'ap_load_balance', 'ap_antenna', 'ap_antenna_gain', 'ap_power_saving', 'ap_wired_uplink', 'ap_wired_downlink', 'ap_ports', 'gateway_lan_status', 'ap_lan_traffic', 'ap_vlan', 'devices', 'device_firmware', 'clients', 'site_client_identity_match', 'client_detail', 'client_connection_history', 'client_history', 'client_timeline', 'client_health', 'client_health_timeline', 'networks', 'network_dhcp_server_capabilities', 'network_dhcp_server_info', 'ssids', 'ssid_configuration', 'wireless_groups', 'ap_radio', 'ap_available_channels', 'ap_scan_status', 'ap_speed_test_results', 'ap_ssid_override_audit_summary', 'ap_channel_changes', 'ap_health', 'ap_health_timeline', 'ap_afc', 'ap_afc_status', 'ap_retry_drop', 'ap_mesh_statistics', 'ap_rf_scan', 'ap_wifi_neighbors', 'gateway_wan_status', 'gateway_wan_health', 'gateway_health', 'gateway_health_timeline', 'gateway_ports', 'gateway_speed_test_results', 'gateway_dhcp_leases', 'gateway_internet_info', 'gateway_ipv6_ip_passthrough', 'switch_ports', 'switch_port_counters', 'switch_port_poe_info', 'switch_port_poe_mode', 'switch_port_status', 'switch_vlans', 'switch_lldp_neighbors', 'switch_health', 'switch_health_timeline', 'switch_sdm_usage', 'switch_cable_test_logs', 'switch_cable_test_full_results', 'switch_cable_test_increment_results', 'switch_cable_test_ports', 'switch_dhcp_users', 'switch_ospf_neighbors', 'switch_port_networks', 'switch_exist_networks', 'switch_networks', 'switch_interfaces', 'switch_routing_table', 'switch_static_routes', 'switch_vrfs', 'switch_vlan_interfaces', 'switch_statistics', 'switch_port_tags', 'gateway_firewall_rules', 'switch_firewall_rules', 'ap_firewall_rules', 'dhcp_leases', 'dns_cache_settings', 'dns_proxy_settings', 'lan_dns_records', 'client_timeline_connect', 'client_timeline_association', 'client_timeline_roaming', 'client_timeline_disconnect', 'site_events', 'site_events_window_summary', 'site_alerts', 'site_alerts_window_summary', 'site_audit_log_window_summary', 'controller_audit_log_window_summary', 'site_rogue_ap_results', 'site_wids_summary', 'site_wids_blacklist_summary', 'controller_status', 'controller_logging', 'controller_certificate', 'device_adopt_result', 'device_mac_type', 'device_link_topology', 'device_radsec_support', 'device_upgrade_result', 'device_timeline', 'device_inventory_summary', 'olt_detail_summary', 'olt_ports_summary', 'msp_olt_detail_summary', 'msp_olt_eth_config_summary', 'msp_olt_site_ports_summary', 'msp_olt_pon_port_config_summary', 'olt_onu_global_status', 'olt_onu_isolation_status', 'olt_eth_config_summary', 'olt_lag_config_summary', 'olt_auto_refresh_summary', 'olt_pon_information_summary', 'olt_pon_port_config_page_summary', 'olt_pon_port_config_summary', 'olt_service_port_profiles_summary', 'olt_onu_inventory_summary', 'olt_onu_auto_auth_status', 'olt_onu_autofind_summary', 'olt_onu_autofind_inventory_summary', 'olt_onu_reboot_status_summary', 'olt_system_info', 'olt_system_info_msp', 'msp_ap_health_detail', 'msp_ap_mesh_statistics', 'msp_gateway_health_detail', 'msp_switch_health_detail', 'msp_ap_health_timeline', 'msp_gateway_health_timeline', 'msp_switch_health_timeline', 'olt_management_interfaces', 'controller_roles', 'controller_available_roles', 'controller_known_devices', 'controller_unknown_devices', 'controller_device_batch_adopt_summary', 'site_pending_devices_summary', 'site_batch_interference_ap_summary', 'site_batch_wifi_interference_summary', 'site_batch_channel_load_summary', 'site_batch_interference_result_summary', 'site_batch_interference_status_summary', 'site_ap_full_channel_detect_status', 'ap_available_channels_summary', 'ap_interference_result_summary', 'ap_channel_load_summary', 'site_lan_network_detail_summary', 'site_stack_connections_summary', 'site_stack_network_summary', 'site_stack_static_routing_summary', 'site_stack_cable_test_log_summary', 'site_stack_ospf_neighbor_summary', 'site_intelli_recover_summary', 'site_port_forwarding_summary', 'site_stack_dhcp_user_summary', 'site_switch_oui_vlan_summary', 'client_health_detail_v2', 'controller_backup_inventory_summary', 'site_backup_inventory_summary', 'site_gateway_webfilter_summary', 'site_ap_webfilter_summary', 'site_url_filter_general_summary', 'site_lan_interface_isolation_summary', 'site_ospf_interface_summary', 'site_gateway_qos_class_summary', 'controller_sdwan_group_summary', 'controller_sdwan_group_devices_summary', 'site_wan_unsupported_function_summary', 'site_mdns_profile_summary', 'controller_try_beta_settings_summary', 'controller_auto_check_upgrade_summary', 'controller_firmware_inventory_summary', 'site_agile_switch_general_config_summary'],
                "openapi_inventory_requires_caller_token": True,
                "implemented_query": OmadaClient.FIXED_PATH,
            })
            return
        if self.path == "/omada/controller-info":
            try:
                result = OmadaClient(OmadaConfig.from_env()).read_controller_info()
            except OmadaError as exc:
                self._send(HTTPStatus.BAD_GATEWAY, {"status": "error", "error": exc.code})
                return
            self._send(HTTPStatus.OK, result)
            return
        doubt_list_match = re.fullmatch(r"/v1/change-plans/([a-z0-9-]+)/in-doubt", self.path)
        doubt_inspect_match = re.fullmatch(r"/v1/change-plans/([a-z0-9-]+)/([0-9a-f]{48})", self.path)
        if doubt_list_match or doubt_inspect_match:
            kind = (doubt_list_match or doubt_inspect_match).group(1)
            if kind not in _CHANGE_PLAN_KINDS:
                self._send(HTTPStatus.NOT_FOUND, {"status": "error", "error": "not_found"})
                return
            if not self._authorized():
                return
            try:
                with _OPENAPI_LOCK:
                    runtime = _journal_runtime()
                    if os.getenv("OMADA_CHANGE_JOURNAL_DIR") and not runtime.ready:
                        self._send(HTTPStatus.SERVICE_UNAVAILABLE, _journal_http_failure())
                        return
                    manager, error_type = _in_doubt_manager(kind)
                    if doubt_list_match:
                        items = manager.list_in_doubt()
                        result = {"status": "ok", "items": [dict(item, outcome="unknown") for item in items]}
                    else:
                        result = manager.inspect_in_doubt(doubt_inspect_match.group(2))
                        result["status"] = "ok"
                        result["outcome"] = "unknown"
            except (ChangeError, DnsCacheChangeError, SsidChangeError,
                    GatewayIpv6ChangeError, PoeChangeError, PortStatusChangeError, BandSteeringChangeError,
                    RrmModeChangeError, SiteLedChangeError, ApAfcChangeError, SiteLldpChangeError,
                    ApChannelLimitChangeError, ApOfdmaChangeError, PortNameChangeError,
                    SiteDpiLoggingChangeError, GatewayVoipChangeError,
                    GatewayTagQosChangeError, SwitchCableTestError,
                    ControllerRadiusProxyChangeError) as exc:
                self._send(_in_doubt_status(str(exc)), {"status": "error", "error": str(exc)})
                return
            except OpenApiError as exc:
                self._send(HTTPStatus.BAD_GATEWAY, {"status": "error", "error": exc.code})
                return
            self._send(HTTPStatus.OK, result)
            return
        if self.path in {"/v1/sites", "/v1/controller/health",
                         "/v1/controller/settings/client-recognition",
                         "/v1/controller/devices/statistics",
                         "/v1/controller/settings/client-active-timeout",
                         "/v1/controller/settings/client-history",
                         "/v1/controller/settings/audit-notification",
                         "/v1/controller/settings/ui-interface",
                         "/v1/controller/settings/retention",
                         "/v1/controller/dst-info",
                         "/v1/controller/settings/experience-improvement",
                         "/v1/controller/client-detail-information",
                         "/v1/controller/settings/general",
                         "/v1/controller/settings/device-access",
                         "/v1/controller/settings/backup-schedule",
                         "/v1/controller/cloud-access",
                         "/v1/controller/settings/device-management",
                         "/v1/controller/cloud-binding",
                         "/v1/controller/maintenance/backup-status",
                         "/v1/controller/maintenance/backup-inventory-summary",
                         "/v1/controller/maintenance/restore-status",
                         "/v1/controller/settings/privacy-policy",
                         "/v1/controller/settings/mail-server-status",
                         "/v1/controller/settings/mfa-status",
                         "/v1/controller/settings/remote-logging",
                         "/v1/controller/settings/remote-logging-tip",
                         "/v1/controller/settings/radius-proxy",
                         "/v1/controller/settings/radius-server",
                         "/v1/controller/settings/upgrade-port",
                         "/v1/controller/settings/portal-port",
                         "/v1/controller/settings/controller-port", "/v1/controller/status",
                         "/v1/controller/scenarios", "/v1/controller/scenario-differences",
                         "/v1/controller/settings/logging", "/v1/controller/settings/certificate",
                         "/v1/controller/roles/summary",
                         "/v1/controller/roles/available-summary",
                         "/v1/controller/devices/known-summary",
                         "/v1/controller/devices/unknown-summary",
                         "/v1/controller/devices/batch-adopt-summary", "/v1/site-templates"} or \
                urlsplit(self.path).path in {"/v1/controller/gateway-wan-status-summary",
                                             "/v1/controller/threat-severity-summary",
                                             "/v1/controller/audit-logs/window",
                                             "/v1/controller/events/window",
                                             "/v1/controller/alerts/window",
                                             "/v1/controller/firmware-upgrades/summary",
                                             "/v1/controller/firmware-upgrade-plans/summary",
                                             "/v1/controller/firmware-preview-settings/summary",
                                             "/v1/controller/automatic-firmware-checks/summary",
                                             "/v1/controller/log-notifications/summary",
                                             "/v1/controller/firmware-upgrade-models/summary", \
                                             "/v1/controller/firmware-inventory-summary", \
                                             "/v1/controller/sdwan-groups/summary"} or \
                urlsplit(self.path).path.startswith("/v1/controller/firmware-upgrades/") or \
                self.path.startswith("/v1/controller/sdwan-groups/") or \
                self.path.startswith("/v1/sites/") or self.path.startswith("/v1/site-templates/") or self.path.startswith("/v1/msp/"):
            self._openapi_get()
            return
        if self.path == "/v1/capabilities":
            self._capabilities_get()
            return
        if self.path == "/v1/diagnostic-capabilities":
            self._diagnostic_capabilities_get()
            return
        cable_status_match = re.fullmatch(
            r"/v1/switch-cable-test-plans/([0-9a-f]{48})/status", self.path)
        if cable_status_match:
            if not self._authorized():
                return
            try:
                with _OPENAPI_LOCK:
                    client = _openapi_client()
                    result = _switch_cable_test_plans(client).status(cable_status_match.group(1))
            except SwitchCableTestError as exc:
                self._send(_in_doubt_status(exc.code), {"status": "error", "error": exc.code})
                return
            except OpenApiError as exc:
                self._send(HTTPStatus.BAD_GATEWAY, {"status": "error", "error": exc.code})
                return
            self._send(HTTPStatus.OK, result)
            return
        if self.path == "/mcp":
            self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"status": "error", "error": "method_not_allowed"})
            return
        self._send(HTTPStatus.NOT_FOUND, {"status": "error", "error": "not_found"})

    def _capabilities_get(self) -> None:
        configured = _caller_token()
        if configured is None:
            self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "error": "route_disabled"})
            return
        authorization = self.headers.get("Authorization", "")
        scheme, separator, supplied = authorization.partition(" ")
        try:
            supplied_bytes = supplied.encode("ascii") if separator and scheme.lower() == "bearer" and len(supplied) <= 4096 else b""
        except UnicodeEncodeError:
            supplied_bytes = b""
        if not hmac.compare_digest(configured, supplied_bytes):
            self._send(HTTPStatus.UNAUTHORIZED, {"status": "error", "error": "unauthorized"})
            return
        try:
            with _OPENAPI_LOCK:
                result = _openapi_client().capabilities()
        except OpenApiError:
            result = OmadaOpenApiClient.capability_catalog()
        self._send(HTTPStatus.OK, result)

    def _diagnostic_capabilities_get(self) -> None:
        if not self._authorized():
            return
        try:
            with _OPENAPI_LOCK:
                catalog = _openapi_client().capabilities()
        except OpenApiError:
            catalog = OmadaOpenApiClient.capability_catalog()
        self._send(HTTPStatus.OK, project_diagnostic_capability_report(catalog))

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/mcp":
            if not self._authorized():
                return
            self._mcp_post()
            return
        doubt_close_match = re.fullmatch(
            r"/v1/change-plans/([a-z0-9-]+)/([0-9a-f]{48})/close", self.path)
        incident_report_comparison_match = re.fullmatch(
            r"/v1/incident-reports/compare", self.path)
        radius_proxy_preview_match = re.fullmatch(
            r"/v1/controller/settings/radius-proxy-preview", self.path)
        radius_proxy_apply_match = re.fullmatch(
            r"/v1/controller-radius-proxy-plans/([0-9a-f]{48})/apply", self.path)
        preview_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/radio-preview", self.path)
        apply_match = re.fullmatch(r"/v1/radio-plans/([0-9a-f]{48})/apply", self.path)
        dns_preview_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/dns/cache-preview", self.path)
        dns_apply_match = re.fullmatch(r"/v1/dns-cache-plans/([0-9a-f]{48})/apply", self.path)
        ssid_preview_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/ssids/([0-9a-f]{24})/enable-preview", self.path)
        ssid_apply_match = re.fullmatch(r"/v1/ssid-plans/([0-9a-f]{48})/apply", self.path)
        gateway_ipv6_preview_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/gateways/([0-9a-f]{24})/ipv6-ip-passthrough-preview",
            self.path)
        gateway_ipv6_apply_match = re.fullmatch(
            r"/v1/gateway-ipv6-plans/([0-9a-f]{48})/apply", self.path)
        poe_preview_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/ports/([0-9]{1,5})/poe-preview",
            self.path)
        poe_apply_match = re.fullmatch(r"/v1/poe-plans/([0-9a-f]{48})/apply", self.path)
        port_status_preview_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/ports/([0-9]{1,5})/status-preview",
            self.path)
        port_status_apply_match = re.fullmatch(r"/v1/switch-port-status-plans/([0-9a-f]{48})/apply", self.path)
        port_name_preview_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/ports/([0-9]{1,5})/name-preview",
            self.path)
        port_name_apply_match = re.fullmatch(r"/v1/switch-port-name-plans/([0-9a-f]{48})/apply", self.path)
        band_steering_preview_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/wifi/band-steering-preview", self.path)
        band_steering_apply_match = re.fullmatch(r"/v1/band-steering-plans/([0-9a-f]{48})/apply", self.path)
        rrm_mode_preview_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/wifi/optimization-preview", self.path)
        rrm_mode_apply_match = re.fullmatch(r"/v1/rrm-mode-plans/([0-9a-f]{48})/apply", self.path)
        site_led_preview_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/led-preview", self.path)
        site_led_apply_match = re.fullmatch(r"/v1/site-led-plans/([0-9a-f]{48})/apply", self.path)
        ap_afc_preview_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/afc-preview", self.path)
        ap_afc_apply_match = re.fullmatch(r"/v1/ap-afc-plans/([0-9a-f]{48})/apply", self.path)
        site_lldp_preview_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/lldp-preview", self.path)
        site_lldp_apply_match = re.fullmatch(r"/v1/site-lldp-plans/([0-9a-f]{48})/apply", self.path)
        site_dpi_preview_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/application-control-preview", self.path)
        site_dpi_apply_match = re.fullmatch(r"/v1/site-dpi-plans/([0-9a-f]{48})/apply", self.path)
        gateway_voip_preview_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/qos/gateway/voip-prioritization-preview", self.path)
        gateway_voip_apply_match = re.fullmatch(
            r"/v1/gateway-voip-plans/([0-9a-f]{48})/apply", self.path)
        gateway_tag_qos_preview_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/qos/gateway/tag-outbound-traffic-preview", self.path)
        gateway_tag_qos_apply_match = re.fullmatch(
            r"/v1/gateway-tag-qos-plans/([0-9a-f]{48})/apply", self.path)
        ap_channel_limit_preview_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/channel-limit-preview", self.path)
        ap_channel_limit_apply_match = re.fullmatch(
            r"/v1/ap-channel-limit-plans/([0-9a-f]{48})/apply", self.path)
        ap_ofdma_preview_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/ofdma-preview", self.path)
        ap_ofdma_apply_match = re.fullmatch(
            r"/v1/ap-ofdma-plans/([0-9a-f]{48})/apply", self.path)
        ap_qos_preview_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/qos-preview", self.path)
        ap_qos_apply_match = re.fullmatch(
            r"/v1/ap-qos-plans/([0-9a-f]{48})/apply", self.path)
        cable_test_preview_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/cable-test-preview", self.path)
        cable_test_apply_match = re.fullmatch(
            r"/v1/switch-cable-test-plans/([0-9a-f]{48})/apply", self.path)
        cable_test_cancel_preview_match = re.fullmatch(
            r"/v1/switch-cable-test-plans/([0-9a-f]{48})/cancel-preview", self.path)
        cable_test_cancel_apply_match = re.fullmatch(
            r"/v1/switch-cable-test-cancel-plans/([0-9a-f]{48})/apply", self.path)
        if (preview_match is None and apply_match is None and
                radius_proxy_preview_match is None and radius_proxy_apply_match is None and
                dns_preview_match is None and
                dns_apply_match is None and ssid_preview_match is None and ssid_apply_match is None and
                gateway_ipv6_preview_match is None and gateway_ipv6_apply_match is None and
                poe_preview_match is None and poe_apply_match is None and
                port_status_preview_match is None and port_status_apply_match is None and
                port_name_preview_match is None and port_name_apply_match is None and
                band_steering_preview_match is None and band_steering_apply_match is None and
                rrm_mode_preview_match is None and rrm_mode_apply_match is None and
                site_led_preview_match is None and site_led_apply_match is None and
                ap_afc_preview_match is None and ap_afc_apply_match is None and
                site_lldp_preview_match is None and site_lldp_apply_match is None and
                site_dpi_preview_match is None and site_dpi_apply_match is None and
                gateway_voip_preview_match is None and gateway_voip_apply_match is None and
                gateway_tag_qos_preview_match is None and gateway_tag_qos_apply_match is None and
                ap_channel_limit_preview_match is None and ap_channel_limit_apply_match is None and
                ap_ofdma_preview_match is None and ap_ofdma_apply_match is None and
                ap_qos_preview_match is None and ap_qos_apply_match is None and
                cable_test_preview_match is None and cable_test_apply_match is None and
                cable_test_cancel_preview_match is None and cable_test_cancel_apply_match is None and
                incident_report_comparison_match is None and
                doubt_close_match is None):
            self.send_error(HTTPStatus.NOT_IMPLEMENTED)
            return
        if not self._authorized():
            return
        if doubt_close_match and doubt_close_match.group(1) not in _CHANGE_PLAN_KINDS:
            self._send(HTTPStatus.NOT_FOUND, {"status": "error", "error": "not_found"})
            return
        try:
            lengths = self.headers.get_all("Content-Length", [])
            if (len(lengths) != 1 or self.headers.get_all("Transfer-Encoding", []) or
                    self.headers.get_all("Content-Type", []) != ["application/json"]):
                raise ChangeError("request_invalid")
            length = lengths[0]
            if not re.fullmatch(r"[0-9]{1,5}", length):
                raise ChangeError("request_invalid")
            size = int(length)
            request_limit = (65_536 if incident_report_comparison_match is not None
                             else _MAX_REQUEST_BYTES)
            if size > request_limit:
                raise ChangeError("request_too_large")
            self.connection.settimeout(5.0)
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ChangeError("request_invalid")
            def object_no_duplicates(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate_key")
                    result[key] = value
                return result
            body = json.loads(raw, object_pairs_hook=object_no_duplicates)
            if not isinstance(body, dict):
                raise ChangeError("request_invalid")
            if incident_report_comparison_match is not None:
                if set(body) != {"reports"}:
                    self._send(HTTPStatus.BAD_REQUEST,
                               {"status": "error", "error": "request_invalid"})
                    return
                try:
                    try:
                        from .incident_report_comparison import (
                            IncidentReportComparisonError, compare_incident_reports,
                        )
                    except ImportError:
                        from incident_report_comparison import (
                            IncidentReportComparisonError, compare_incident_reports,
                        )
                    result = compare_incident_reports(body["reports"])
                except IncidentReportComparisonError as exc:
                    self._send(HTTPStatus.BAD_REQUEST,
                               {"status": "error", "error": exc.code})
                    return
                self._send(HTTPStatus.OK, result)
                return
            with _OPENAPI_LOCK:
                client = _openapi_client()
                if doubt_close_match:
                    runtime = _journal_runtime(client)
                    if os.getenv("OMADA_CHANGE_JOURNAL_DIR") and not runtime.ready:
                        self._send(HTTPStatus.SERVICE_UNAVAILABLE, _journal_http_failure())
                        return
                    manager, error_type = _in_doubt_manager(doubt_close_match.group(1))
                    if body != {"confirmation": "outcome_unknown_no_retry"}:
                        self._send(HTTPStatus.CONFLICT,
                                   {"status": "error", "error": "operator_confirmation_required"})
                        return
                    try:
                        result = manager.close_in_doubt(
                            doubt_close_match.group(2), body["confirmation"])
                    except error_type as exc:
                        self._send(_in_doubt_status(str(exc)),
                                   {"status": "error", "error": str(exc)})
                        return
                    result["outcome"] = "unknown"
                    result["status"] = "ok"
                    status = HTTPStatus.OK
                elif gateway_ipv6_preview_match or gateway_ipv6_apply_match:
                    plans = _gateway_ipv6_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if gateway_ipv6_preview_match:
                        if set(body) != {"changes"}:
                            raise GatewayIpv6ChangeError("request_invalid")
                        result = plans.preview(gateway_ipv6_preview_match.group(1),
                                               gateway_ipv6_preview_match.group(2),
                                               body["changes"])
                    else:
                        result = _apply_with_operator_approval(client, plans, "gateway-ipv6",
                                                              gateway_ipv6_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif site_lldp_preview_match or site_lldp_apply_match:
                    plans = _site_lldp_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if site_lldp_preview_match:
                        if set(body) != {"changes", "disruption_confirmed"}:
                            raise SiteLldpChangeError("request_invalid")
                        result = plans.preview(site_lldp_preview_match.group(1), body["changes"],
                                               disruption_confirmed=body["disruption_confirmed"])
                    else:
                        result = _apply_with_operator_approval(client, plans, "site-lldp",
                                                              site_lldp_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif site_dpi_preview_match or site_dpi_apply_match:
                    plans = _site_dpi_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if site_dpi_preview_match:
                        if set(body) != {"changes", "disruption_confirmed"}:
                            raise SiteDpiLoggingChangeError("request_invalid")
                        result = plans.preview(
                            site_dpi_preview_match.group(1), body["changes"],
                            disruption_confirmed=body["disruption_confirmed"])
                    else:
                        result = _apply_with_operator_approval(
                            client, plans, "site-dpi", site_dpi_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif gateway_voip_preview_match or gateway_voip_apply_match:
                    plans = _gateway_voip_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if gateway_voip_preview_match:
                        if set(body) != {"changes", "disruption_confirmed"}:
                            raise GatewayVoipChangeError("request_invalid")
                        result = plans.preview(
                            gateway_voip_preview_match.group(1), body["changes"],
                            disruption_confirmed=body["disruption_confirmed"])
                    else:
                        result = _apply_with_operator_approval(
                            client, plans, "gateway-voip", gateway_voip_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif gateway_tag_qos_preview_match or gateway_tag_qos_apply_match:
                    plans = _gateway_tag_qos_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if gateway_tag_qos_preview_match:
                        if set(body) != {"changes", "disruption_confirmed"}:
                            raise GatewayTagQosChangeError("request_invalid")
                        result = plans.preview(
                            gateway_tag_qos_preview_match.group(1), body["changes"],
                            disruption_confirmed=body["disruption_confirmed"])
                    else:
                        result = _apply_with_operator_approval(
                            client, plans, "gateway-tag-qos",
                            gateway_tag_qos_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif ap_channel_limit_preview_match or ap_channel_limit_apply_match:
                    plans = _ap_channel_limit_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if ap_channel_limit_preview_match:
                        if set(body) != {"changes", "disruption_confirmed"}:
                            raise ApChannelLimitChangeError("request_invalid")
                        result = plans.preview(
                            ap_channel_limit_preview_match.group(1),
                            ap_channel_limit_preview_match.group(2), body["changes"],
                            disruption_confirmed=body["disruption_confirmed"])
                    else:
                        result = _apply_with_operator_approval(
                            client, plans, "ap-channel-limit",
                            ap_channel_limit_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif ap_ofdma_preview_match or ap_ofdma_apply_match:
                    plans = _ap_ofdma_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if ap_ofdma_preview_match:
                        if set(body) != {"changes", "disruption_confirmed"}:
                            raise ApOfdmaChangeError("request_invalid")
                        result = plans.preview(
                            ap_ofdma_preview_match.group(1),
                            ap_ofdma_preview_match.group(2), body["changes"],
                            disruption_confirmed=body["disruption_confirmed"])
                    else:
                        result = _apply_with_operator_approval(
                            client, plans, "ap-ofdma", ap_ofdma_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif ap_qos_preview_match or ap_qos_apply_match:
                    plans = _ap_qos_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if ap_qos_preview_match:
                        if set(body) != {"changes", "disruption_confirmed"}:
                            raise ApQosChangeError("request_invalid")
                        result = plans.preview(ap_qos_preview_match.group(1),
                            ap_qos_preview_match.group(2), body["changes"],
                            disruption_confirmed=body["disruption_confirmed"])
                    else:
                        result = _apply_with_operator_approval(
                            client, plans, "ap-qos", ap_qos_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif radius_proxy_preview_match or radius_proxy_apply_match:
                    plans = _controller_radius_proxy_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if radius_proxy_preview_match:
                        if set(body) != {"changes"}:
                            raise ControllerRadiusProxyChangeError("request_invalid")
                        result = plans.preview(body["changes"])
                    else:
                        result = _apply_with_operator_approval(
                            client, plans, "controller-radius-proxy",
                            radius_proxy_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif (cable_test_preview_match or cable_test_apply_match or
                      cable_test_cancel_preview_match or cable_test_cancel_apply_match):
                    plans = _switch_cable_test_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if cable_test_preview_match:
                        if set(body) != {"port", "disruption_confirmed"}:
                            raise SwitchCableTestError("request_invalid")
                        result = plans.preview(cable_test_preview_match.group(1),
                            cable_test_preview_match.group(2), body["port"],
                            body["disruption_confirmed"])
                    elif cable_test_apply_match:
                        result = _apply_with_operator_approval(client, plans,
                            "switch-cable-test", cable_test_apply_match.group(1), body)
                    elif cable_test_cancel_preview_match:
                        if set(body) != {"disruption_confirmed"}:
                            raise SwitchCableTestError("request_invalid")
                        result = plans.preview_cancel(cable_test_cancel_preview_match.group(1),
                                                     body["disruption_confirmed"])
                    else:
                        result = _apply_with_operator_approval(client, plans,
                            "switch-cable-test-cancel", cable_test_cancel_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif ap_afc_preview_match or ap_afc_apply_match:
                    plans = _ap_afc_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if ap_afc_preview_match:
                        if set(body) != {"changes", "disruption_confirmed"}:
                            raise ApAfcChangeError("request_invalid")
                        result = plans.preview(ap_afc_preview_match.group(1), ap_afc_preview_match.group(2),
                                               body["changes"], disruption_confirmed=body["disruption_confirmed"])
                    else:
                        result = _apply_with_operator_approval(client, plans, "ap-afc",
                                                              ap_afc_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif site_led_preview_match or site_led_apply_match:
                    plans = _site_led_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if site_led_preview_match:
                        if set(body) != {"changes"}:
                            raise SiteLedChangeError("request_invalid")
                        result = plans.preview(site_led_preview_match.group(1), body["changes"])
                    else:
                        result = _apply_with_operator_approval(client, plans, "site-led",
                                                              site_led_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif rrm_mode_preview_match or rrm_mode_apply_match:
                    plans = _rrm_mode_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if rrm_mode_preview_match:
                        if set(body) != {"changes", "disruption_confirmed"}:
                            raise RrmModeChangeError("request_invalid")
                        result = plans.preview(rrm_mode_preview_match.group(1), body["changes"],
                                               disruption_confirmed=body["disruption_confirmed"])
                    else:
                        result = _apply_with_operator_approval(client, plans, "rrm-mode",
                                                              rrm_mode_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif band_steering_preview_match or band_steering_apply_match:
                    plans = _band_steering_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if band_steering_preview_match:
                        if set(body) != {"changes", "disruption_confirmed"}:
                            raise BandSteeringChangeError("request_invalid")
                        result = plans.preview(band_steering_preview_match.group(1), body["changes"],
                                               disruption_confirmed=body["disruption_confirmed"])
                    else:
                        result = _apply_with_operator_approval(client, plans, "band-steering",
                                                              band_steering_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif port_status_preview_match or port_status_apply_match:
                    plans = _port_status_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if port_status_preview_match:
                        if set(body) != {"changes", "disruption_confirmed"}:
                            raise PortStatusChangeError("request_invalid")
                        result = plans.preview(port_status_preview_match.group(1),
                                               port_status_preview_match.group(2),
                                               int(port_status_preview_match.group(3)),
                                               body["changes"],
                                               disruption_confirmed=body["disruption_confirmed"])
                    else:
                        result = _apply_with_operator_approval(client, plans, "switch-port-status",
                                                              port_status_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif port_name_preview_match or port_name_apply_match:
                    plans = _port_name_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if port_name_preview_match:
                        if set(body) != {"changes"}:
                            raise PortNameChangeError("request_invalid")
                        result = plans.preview(port_name_preview_match.group(1),
                                               port_name_preview_match.group(2),
                                               int(port_name_preview_match.group(3)),
                                               body["changes"])
                    else:
                        result = _apply_with_operator_approval(
                            client, plans, "switch-port-name", port_name_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif poe_preview_match or poe_apply_match:
                    plans = _poe_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if poe_preview_match:
                        if set(body) != {"changes"}:
                            raise PoeChangeError("request_invalid")
                        result = plans.preview(poe_preview_match.group(1),
                                               poe_preview_match.group(2),
                                               int(poe_preview_match.group(3)),
                                               body["changes"])
                    else:
                        result = _apply_with_operator_approval(client, plans, "poe",
                                                              poe_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif ssid_preview_match or ssid_apply_match:
                    plans = _ssid_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if ssid_preview_match:
                        if set(body) != {"changes"}:
                            raise SsidChangeError("request_invalid")
                        result = plans.preview(ssid_preview_match.group(1), ssid_preview_match.group(2),
                                               body["changes"])
                    else:
                        result = _apply_with_operator_approval(client, plans, "ssid",
                                                              ssid_apply_match.group(1), body)
                    status = HTTPStatus.OK
                elif dns_preview_match or dns_apply_match:
                    plans = _dns_cache_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if dns_preview_match:
                        if set(body) != {"changes"}:
                            raise DnsCacheChangeError("request_invalid")
                        result = plans.preview(dns_preview_match.group(1), body["changes"])
                    else:
                        result = _apply_with_operator_approval(client, plans, "dns-cache",
                                                              dns_apply_match.group(1), body)
                    status = HTTPStatus.OK
                else:
                    plans = _radio_plans(client)
                    plans.writes_enabled = _effective_writes(client)
                    if preview_match:
                        if set(body) != {"changes"}:
                            raise ChangeError("request_invalid")
                        result = plans.preview(preview_match.group(1), preview_match.group(2), body["changes"])
                        status = HTTPStatus.OK
                    else:
                        result = _apply_with_operator_approval(client, plans, "radio",
                                                              apply_match.group(1), body)
                        status = HTTPStatus.OK
                if radius_proxy_preview_match:
                    result["approval_request"] = build_approval_summary(
                        "controller-radius-proxy", result["plan_id"], plans)
                elif (preview_match or dns_preview_match or ssid_preview_match or
                        gateway_ipv6_preview_match or poe_preview_match or port_status_preview_match or
                        port_name_preview_match or
                        band_steering_preview_match or rrm_mode_preview_match or site_led_preview_match or
                        ap_afc_preview_match or site_lldp_preview_match or
                        site_dpi_preview_match or
                        gateway_voip_preview_match or
                        gateway_tag_qos_preview_match or
                        ap_channel_limit_preview_match or ap_ofdma_preview_match or ap_qos_preview_match):
                    kind = ("radio" if preview_match else "dns-cache" if dns_preview_match else
                            "ssid" if ssid_preview_match else "gateway-ipv6" if gateway_ipv6_preview_match else
                            "poe" if poe_preview_match else "switch-port-status" if port_status_preview_match else
                            "switch-port-name" if port_name_preview_match else
                            "band-steering" if band_steering_preview_match else "rrm-mode" if rrm_mode_preview_match else
                            "site-led" if site_led_preview_match else "ap-afc" if ap_afc_preview_match else
                            "site-lldp" if site_lldp_preview_match else
                            "site-dpi" if site_dpi_preview_match else
                            "gateway-voip" if gateway_voip_preview_match else
                            "gateway-tag-qos" if gateway_tag_qos_preview_match else
                            "ap-channel-limit" if ap_channel_limit_preview_match else
                            "ap-qos" if ap_qos_preview_match else "ap-ofdma")
                    result["approval_request"] = build_approval_summary(kind, result["plan_id"], plans)
                elif cable_test_preview_match:
                    result["approval_request"] = build_approval_summary(
                        "switch-cable-test", result["plan_id"], plans)
                elif cable_test_cancel_preview_match:
                    result["approval_request"] = build_approval_summary(
                        "switch-cable-test-cancel", result["plan_id"], plans)
        except (OperatorApprovalError, ApprovalPlanError) as exc:
            code = str(exc)
            status = HTTPStatus.SERVICE_UNAVAILABLE if code.startswith("operator_key_") else HTTPStatus.CONFLICT
            self._send(status, {"status": "error", "error": code})
            return
        except SwitchCableTestError as exc:
            code = exc.code
            status = (HTTPStatus.CONFLICT if code in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "cable_test_outcome_unknown", "cable_test_not_cancellable"
            } else HTTPStatus.SERVICE_UNAVAILABLE if code.startswith("journal_") else HTTPStatus.BAD_REQUEST)
            self._send(status, {"status": "error", "error": code})
            return
        except ControllerRadiusProxyChangeError as exc:
            code = str(exc)
            status = (HTTPStatus.SERVICE_UNAVAILABLE if code.startswith("journal_") else
                      HTTPStatus.CONFLICT if code in {
                          "writes_disabled", "plan_unknown", "plan_already_consumed",
                          "plan_expired", "state_changed", "change_in_doubt",
                          "plan_capacity_reached", "journal_required"} else
                      HTTPStatus.BAD_REQUEST)
            self._send(status, {"status": "error", "error": code})
            return
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError, OSError):
            self._send(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "request_invalid"})
            return
        except ChangeError as exc:
            status = HTTPStatus.CONFLICT if exc.args and exc.args[0] in {"writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired", "state_changed", "change_in_doubt"} else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except DnsCacheChangeError as exc:
            status = HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except SsidChangeError as exc:
            status = HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except GatewayIpv6ChangeError as exc:
            status = HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except SiteLldpChangeError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if str(exc).startswith("journal_") else HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except ApChannelLimitChangeError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if str(exc).startswith("journal_") else HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except ApOfdmaChangeError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if str(exc).startswith("journal_") else HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "ofdma_support_state_changed", "change_in_doubt",
                "plan_capacity_reached", "ofdma_band_not_reported_supported"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except ApQosChangeError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if str(exc).startswith("journal_") else HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached",
                "ap_qos_band_not_reported_supported"} else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except ApAfcChangeError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if str(exc).startswith("journal_") else HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except SiteLedChangeError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if str(exc).startswith("journal_") else HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except RrmModeChangeError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if str(exc).startswith("journal_") else HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except BandSteeringChangeError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if str(exc).startswith("journal_") else HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except PortStatusChangeError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if str(exc).startswith("journal_") else HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except SiteDpiLoggingChangeError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if str(exc).startswith("journal_") else HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except GatewayVoipChangeError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if str(exc).startswith("journal_") else HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except GatewayTagQosChangeError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if str(exc).startswith("journal_") else HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except PortNameChangeError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if str(exc).startswith("journal_") else HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except PoeChangeError as exc:
            status = HTTPStatus.CONFLICT if exc.args and exc.args[0] in {
                "writes_disabled", "plan_unknown", "plan_already_consumed", "plan_expired",
                "state_changed", "change_in_doubt", "plan_capacity_reached"
            } else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": str(exc)})
            return
        except OpenApiError as exc:
            self._send(HTTPStatus.BAD_GATEWAY, {"status": "error", "error": exc.code})
            return
        self._send(status, result)

    def _mcp_post(self) -> None:
        origin = self.headers.get("Origin")
        length_header = self.headers.get("Content-Length", "")
        if not length_header.isascii() or not length_header.isdigit():
            self._send(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "content_length_invalid"})
            return
        length = int(length_header)
        if length > 65_536:
            self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"status": "error", "error": "request_too_large"})
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._send(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"status": "error", "error": "content_type_invalid"})
            return
        try:
            request = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "json_invalid"})
            return
        try:
            response = handle_mcp_request(request, origin, REGISTRY, self._mcp_read,
                                          server_version=VERSION, invoke_action=self._mcp_action)
        except McpRequestError as exc:
            status = HTTPStatus.FORBIDDEN if exc.code == "origin_not_allowed" else HTTPStatus.BAD_REQUEST
            self._send(status, {"status": "error", "error": exc.code})
            return
        if response is None:
            self.send_response(HTTPStatus.ACCEPTED)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._send(HTTPStatus.OK, response)

    def _mcp_read(self, operation_id: str, arguments: dict[str, str]) -> dict[str, object]:
        if operation_id == "change_journal_summary":
            with _OPENAPI_LOCK:
                return _read_change_journal_summary()
        if operation_id == "site_capability_comparison":
            refs = arguments.get("site_refs", "").split(",")
            try:
                with _OPENAPI_LOCK:
                    return _openapi_client().read_site_capability_comparison(refs)
            except OpenApiError as exc:
                return {"status": "error", "error": exc.code}
        if operation_id == "site_client_outage_overlap_summary":
            if set(arguments) != {"site_ref", "client_refs", "start_ms", "end_ms"}:
                return {"status": "error", "error": "arguments_invalid"}
            client_refs = arguments["client_refs"].split(",")
            if (not 2 <= len(client_refs) <= 16 or
                    any(not re.fullmatch(r"[0-9a-f]{24}", ref) for ref in client_refs) or
                    len(set(client_refs)) != len(client_refs) or
                    not re.fullmatch(r"[0-9]{12,13}", arguments["start_ms"]) or
                    not re.fullmatch(r"[0-9]{12,13}", arguments["end_ms"])):
                return {"status": "error", "error": "arguments_invalid"}
            try:
                with _OPENAPI_LOCK:
                    return _openapi_client().read_site_client_outage_overlap_summary(
                        arguments["site_ref"], client_refs, int(arguments["start_ms"]),
                        int(arguments["end_ms"]))
            except OpenApiError as exc:
                return {"status": "error", "error": exc.code}
        if operation_id == "site_client_roaming_backtrack_summary":
            if set(arguments) != {"site_ref", "client_refs", "start_ms", "end_ms"}:
                return {"status": "error", "error": "arguments_invalid"}
            client_refs = arguments["client_refs"].split(",")
            if (not 1 <= len(client_refs) <= 16 or
                    any(not re.fullmatch(r"[0-9a-f]{24}", ref) for ref in client_refs) or
                    len(set(client_refs)) != len(client_refs) or
                    not re.fullmatch(r"[0-9]{12,13}", arguments["start_ms"]) or
                    not re.fullmatch(r"[0-9]{12,13}", arguments["end_ms"])):
                return {"status": "error", "error": "arguments_invalid"}
            try:
                with _OPENAPI_LOCK:
                    return _openapi_client().read_site_client_roaming_backtrack_summary(
                        arguments["site_ref"], client_refs, int(arguments["start_ms"]),
                        int(arguments["end_ms"]))
            except OpenApiError as exc:
                return {"status": "error", "error": exc.code}
        if operation_id == "site_ap_uplink_path_summary":
            if (not isinstance(arguments, dict) or
                    set(arguments) != {"site_ref", "device_refs"}):
                return {"status": "error", "error": "arguments_invalid"}
            device_refs = arguments["device_refs"].split(",")
            if (not 1 <= len(device_refs) <= 16 or
                    any(not re.fullmatch(r"[0-9a-f]{24}", ref) for ref in device_refs) or
                    len(set(device_refs)) != len(device_refs)):
                return {"status": "error", "error": "arguments_invalid"}
            try:
                with _OPENAPI_LOCK:
                    return _openapi_client().read_site_ap_uplink_path_summary(
                        arguments["site_ref"], device_refs)
            except OpenApiError as exc:
                return {"status": "error", "error": exc.code}
        if operation_id == "site_channel_reuse_summary":
            if set(arguments) != {"site_ref", "device_refs"}:
                return {"status": "error", "error": "arguments_invalid"}
            device_refs = arguments["device_refs"].split(",")
            if (not 1 <= len(device_refs) <= 16 or
                    any(not re.fullmatch(r"[0-9a-f]{24}", ref) for ref in device_refs) or
                    len(set(device_refs)) != len(device_refs)):
                return {"status": "error", "error": "arguments_invalid"}
            try:
                with _OPENAPI_LOCK:
                    return _openapi_client().read_site_channel_reuse_summary(
                        arguments["site_ref"], device_refs)
            except OpenApiError as exc:
                return {"status": "error", "error": exc.code}
        if operation_id == "diagnostic_capability_summary":
            try:
                with _OPENAPI_LOCK:
                    catalog = _openapi_client().capabilities()
            except OpenApiError:
                catalog = OmadaOpenApiClient.capability_catalog()
            return project_diagnostic_capability_report(catalog)
        if operation_id == "capability_catalog":
            try:
                with _OPENAPI_LOCK:
                    return _openapi_client().capabilities()
            except OpenApiError:
                return OmadaOpenApiClient.capability_catalog()
        if operation_id in {"wifi_diagnose_site", "wifi_diagnose_ap", "wifi_diagnose_client"}:
            return self._mcp_wifi_diagnose(
                arguments, include_ap=operation_id == "wifi_diagnose_ap",
                include_client=operation_id == "wifi_diagnose_client")
        if operation_id == "wifi_compare_aps":
            return self._mcp_wifi_compare_aps(arguments)
        if operation_id == "network_diagnose_gateway":
            return self._mcp_network_diagnose_gateway(arguments)
        if operation_id == "network_diagnose_switch":
            return self._mcp_network_diagnose_switch(arguments)
        if operation_id == "network_overview":
            return self._mcp_network_overview(arguments)
        if operation_id == "site_outage_summary":
            try:
                with _OPENAPI_LOCK:
                    return _openapi_client().read_site_outage_summary(
                        arguments["site_ref"], int(arguments["start_ms"]),
                        int(arguments["end_ms"]))
            except (KeyError, ValueError, OpenApiError) as exc:
                code = str(exc) if isinstance(exc, OpenApiError) else "arguments_invalid"
                return {"status": "error", "error": code}
        if operation_id == "gateway_wan_incident_window":
            try:
                with _OPENAPI_LOCK:
                    return _openapi_client().read_gateway_wan_incident_window(
                        arguments["site_ref"], arguments["gateway_ref"],
                        int(arguments["start_ms"]), int(arguments["end_ms"]))
            except (KeyError, ValueError, OpenApiError) as exc:
                code = str(exc) if isinstance(exc, OpenApiError) else "arguments_invalid"
                return {"status": "error", "error": code}
        if operation_id == "site_dhcp_pool_utilization":
            if set(arguments) != {"site_ref"}:
                return {"status": "error", "error": "arguments_invalid"}
            try:
                with _OPENAPI_LOCK:
                    return _openapi_client().read_site_dhcp_pool_utilization(
                        arguments["site_ref"])
            except OpenApiError as exc:
                return {"status": "error", "error": exc.code}
        if operation_id == "site_ap_quality_window":
            if set(arguments) != {"site_ref"}:
                return {"status": "error", "error": "arguments_invalid"}
            try:
                with _OPENAPI_LOCK:
                    return _openapi_client().read_site_ap_quality_window(arguments["site_ref"])
            except OpenApiError as exc:
                return {"status": "error", "error": exc.code}
        if operation_id == "site_switch_health_history":
            if set(arguments) != {"site_ref"}:
                return {"status": "error", "error": "arguments_invalid"}
            try:
                with _OPENAPI_LOCK:
                    return _openapi_client().read_site_switch_health_history(
                        arguments["site_ref"])
            except OpenApiError as exc:
                return {"status": "error", "error": exc.code}
        if operation_id == "site_firmware_summary":
            if set(arguments) != {"site_ref"}:
                return {"status": "error", "error": "arguments_invalid"}
            try:
                with _OPENAPI_LOCK:
                    return _openapi_client().read_site_firmware_summary(arguments["site_ref"])
            except OpenApiError as exc:
                return {"status": "error", "error": exc.code}
        if operation_id == "site_switch_port_anomaly_summary":
            if set(arguments) != {"site_ref"}:
                return {"status": "error", "error": "arguments_invalid"}
            try:
                with _OPENAPI_LOCK:
                    return _openapi_client().read_site_switch_port_anomaly_summary(
                        arguments["site_ref"])
            except OpenApiError as exc:
                return {"status": "error", "error": exc.code}
        if operation_id == "ssid_network_summary":
            return self._mcp_ssid_network_summary(arguments)
        try:
            operation = REGISTRY.get(operation_id)
        except RegistryError as exc:
            raise McpRequestError("tool_unknown") from exc
        if (operation.public_method != "GET" or
                (operation.upstream_method != "GET" and
                 not (operation.operation_id == "site_batch_interference_status_summary" and
                      operation.upstream_method == "POST"))):
            raise McpRequestError("tool_not_read_only")
        route = operation.public_template
        path_arguments = set(re.findall(r"\{([a-z][a-z0-9_]*)\}", operation.public_template))
        for key, value in arguments.items():
            route = route.replace("{" + key + "}", value)
        query_arguments = set(arguments) - path_arguments
        if query_arguments:
            route += "?" + urlencode({key: arguments[key] for key in query_arguments})
        if "{" in route or "}" in route or not route.startswith("/v1/"):
            raise McpRequestError("tool_route_invalid")
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=15)
        try:
            connection.request(
                "GET",
                route,
                headers={
                    "Authorization": self.headers.get("Authorization", ""),
                    "Accept": "application/json",
                },
            )
            upstream = connection.getresponse()
            raw = upstream.read(_MAX_HTTP_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_HTTP_RESPONSE_BYTES:
                return {"status": "error", "error": "response_too_large"}
            try:
                result = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return {"status": "error", "error": "connector_response_invalid"}
            if not isinstance(result, dict):
                return {"status": "error", "error": "connector_response_invalid"}
            if upstream.status >= 400 and "status" not in result:
                return {"status": "error", "error": f"connector_http_{upstream.status}"}
            return result
        except (OSError, http.client.HTTPException):
            return {"status": "error", "error": "connector_internal_request_failed"}
        finally:
            connection.close()

    def _mcp_action(self, action: str, arguments: dict[str, object]) -> dict[str, object]:
        plan_id = str(arguments.get("plan_id", ""))
        if action == "controller_radius_proxy_preview":
            route, method, body = "/v1/controller/settings/radius-proxy-preview", "POST", {
                "changes": arguments["changes"]}
        elif action == "controller_radius_proxy_apply":
            route, method, body = f"/v1/controller-radius-proxy-plans/{plan_id}/apply", "POST", {
                "approval": arguments["approval"]}
        elif action == "preview":
            route = f"/v1/sites/{arguments['site_ref']}/switches/{arguments['switch_ref']}/cable-test-preview"
            method, body = "POST", {"port": arguments["port"],
                                     "disruption_confirmed": arguments["disruption_confirmed"]}
        elif action == "status":
            route, method, body = f"/v1/switch-cable-test-plans/{plan_id}/status", "GET", None
        elif action == "cancel_preview":
            route, method, body = f"/v1/switch-cable-test-plans/{plan_id}/cancel-preview", "POST", {"disruption_confirmed": True}
        elif action == "apply":
            route, method, body = f"/v1/switch-cable-test-plans/{plan_id}/apply", "POST", {"approval": arguments["approval"]}
        elif action == "cancel_apply":
            route, method, body = f"/v1/switch-cable-test-cancel-plans/{plan_id}/apply", "POST", {"approval": arguments["approval"]}
        else:
            return {"status": "error", "error": "action_unknown"}
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=15)
        try:
            payload = json.dumps(body, separators=(",", ":")) if body is not None else None
            headers = {"Authorization": self.headers.get("Authorization", ""), "Accept": "application/json"}
            if payload is not None:
                headers["Content-Type"] = "application/json"
            connection.request(method, route, body=payload, headers=headers)
            response = connection.getresponse()
            raw = response.read(_MAX_HTTP_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_HTTP_RESPONSE_BYTES:
                return {"status": "error", "error": "response_too_large"}
            result = json.loads(raw)
            if not isinstance(result, dict):
                return {"status": "error", "error": "connector_response_invalid"}
            return result
        except (OSError, http.client.HTTPException, json.JSONDecodeError, UnicodeDecodeError):
            return {"status": "error", "error": "connector_internal_request_failed"}
        finally:
            connection.close()

    def _mcp_wifi_diagnose(self, arguments: dict[str, str], *,
                           include_ap: bool = False,
                           include_client: bool = False) -> dict[str, object]:
        try:
            from tools import wifi_diagnose
        except ImportError:
            return {"status": "error", "error": "diagnostic_unavailable"}
        site_ref = arguments.get("site_ref", "")
        allowed_paths = {"/v1/sites"} | {
            template.format(site_ref=site_ref)
            for _, template in wifi_diagnose._DIAGNOSTIC_ROUTES
        }
        client_ref = arguments.get("client_ref")
        if include_client and client_ref is not None:
            allowed_paths.add(f"/v1/sites/{site_ref}/clients")
            allowed_paths.add(f"/v1/sites/{site_ref}/clients/{client_ref}/connections")
            allowed_paths.add(f"/v1/sites/{site_ref}/clients/{client_ref}/health/timeline")
            allowed_paths.add(f"/v1/sites/{site_ref}/clients/{client_ref}/history")
            allowed_paths.update({
                f"/v1/sites/{site_ref}/clients/{client_ref}/timeline/{kind}"
                for kind in ("connect", "association", "roaming", "disconnect")
            })
        ap_ref = arguments.get("ap_ref")
        if include_ap and ap_ref is not None:
            allowed_paths.add(f"/v1/sites/{site_ref}/devices")
            allowed_paths.update({
                f"/v1/sites/{site_ref}/aps/{ap_ref}/health",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/health/timeline",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/radio-config",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/rf-scan",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/wifi-neighbors",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/lan-traffic",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/speed-test-results",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/wired-downlink",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/wired-uplink",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/ports",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/lldp-config",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/port-vlans",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/wlan-overrides",
            })

        current_inventory = None
        if include_client:
            try:
                with _OPENAPI_LOCK:
                    current_inventory = _openapi_client().current_client_diagnostic_inventory(
                        site_ref)
            except OpenApiError as exc:
                return {"status": "error", "error": exc.code,
                        "capability_status": "unknown"}

        def fixed_read(path: str) -> object:
            if path not in allowed_paths:
                raise wifi_diagnose.CliError("connector_unavailable")
            connection = http.client.HTTPConnection(
                "127.0.0.1", self.server.server_port, timeout=15)
            try:
                connection.request("GET", path, headers={
                    "Authorization": self.headers.get("Authorization", ""),
                    "Accept": "application/json",
                })
                response = connection.getresponse()
                raw = response.read(wifi_diagnose.MAX_RESPONSE_BYTES + 1)
                if len(raw) > wifi_diagnose.MAX_RESPONSE_BYTES:
                    raise wifi_diagnose.CliError("response_too_large")
                if response.status != HTTPStatus.OK:
                    raise wifi_diagnose.CliError("connector_http_error")
                try:
                    value = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise wifi_diagnose.CliError("response_invalid") from None
                if not isinstance(value, dict):
                    raise wifi_diagnose.CliError("response_invalid")
                return value
            except (OSError, http.client.HTTPException):
                raise wifi_diagnose.CliError("connector_unavailable") from None
            finally:
                connection.close()

        try:
            return wifi_diagnose.run(
                site_ref, "", ap_ref=ap_ref if include_ap else None,
                client_ref=client_ref if include_client else None,
                client_timeline=include_client, requester=fixed_read,
                compact_client_timeline=include_client,
                include_wlan_policy_context=not (include_client or include_ap),
                current_inventory=current_inventory)
        except wifi_diagnose.CliError as exc:
            return {"status": "error", "error": exc.code,
                    "capability_status": "unknown"}

    def _mcp_wifi_compare_aps(self, arguments: dict[str, str]) -> dict[str, object]:
        try:
            from tools import wifi_diagnose
        except ImportError:
            return {"status": "error", "error": "diagnostic_unavailable"}
        site_ref = arguments.get("site_ref", "")
        ap_refs = [arguments.get("ap_ref_a", ""), arguments.get("ap_ref_b", "")]
        allowed_paths = {"/v1/sites", f"/v1/sites/{site_ref}/devices"}
        for ap_ref in ap_refs:
            allowed_paths.update({
                f"/v1/sites/{site_ref}/aps/{ap_ref}/health",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/radio-config",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/rf-scan",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/wifi-neighbors",
                f"/v1/sites/{site_ref}/aps/{ap_ref}/lan-traffic",
            })

        def fixed_read(path: str) -> object:
            if path not in allowed_paths:
                raise wifi_diagnose.CliError("connector_unavailable")
            connection = http.client.HTTPConnection(
                "127.0.0.1", self.server.server_port, timeout=15)
            try:
                connection.request("GET", path, headers={
                    "Authorization": self.headers.get("Authorization", ""),
                    "Accept": "application/json",
                })
                response = connection.getresponse()
                raw = response.read(wifi_diagnose.MAX_RESPONSE_BYTES + 1)
                if len(raw) > wifi_diagnose.MAX_RESPONSE_BYTES:
                    raise wifi_diagnose.CliError("response_too_large")
                if response.status != HTTPStatus.OK:
                    code, upstream_status, upstream_code = _safe_upstream_error(
                        response.status, raw)
                    raise wifi_diagnose.CliError(
                        code, upstream_http_status=upstream_status,
                        upstream_error_code=upstream_code)
                try:
                    value = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise wifi_diagnose.CliError("response_invalid") from None
                if not isinstance(value, dict):
                    raise wifi_diagnose.CliError("response_invalid")
                return value
            except (OSError, http.client.HTTPException):
                raise wifi_diagnose.CliError("connector_unavailable") from None
            finally:
                connection.close()

        try:
            return wifi_diagnose.compare_aps(site_ref, ap_refs, requester=fixed_read)
        except wifi_diagnose.CliError as exc:
            return {"status": "error", "error": exc.code,
                    "capability_status": "unknown"}

    def _mcp_network_diagnose_gateway(self, arguments: dict[str, str]) -> dict[str, object]:
        try:
            from app import network_diagnose
        except ImportError:
            return {"status": "error", "error": "diagnostic_unavailable"}
        site_ref, gateway_ref = arguments["site_ref"], arguments["gateway_ref"]
        root = f"/v1/sites/{site_ref}/gateways/{gateway_ref}"
        allowed_paths = {
            "/v1/sites", f"/v1/sites/{site_ref}/devices",
            root + "/wan-status", root + "/wan-health",
            root + "/health", root + "/health/timeline", root + "/lan-status",
            root + "/ports",
            root + "/speed-test-results",
            root + "/internet-info",
            f"/v1/sites/{site_ref}/settings/existence", f"/v1/sites/{site_ref}/capabilities",
        }

        def fixed_read(path: str) -> object:
            if path not in allowed_paths:
                raise network_diagnose.NetworkDiagnoseError("connector_unavailable")
            connection = http.client.HTTPConnection(
                "127.0.0.1", self.server.server_port, timeout=15)
            try:
                connection.request("GET", path, headers={
                    "Authorization": self.headers.get("Authorization", ""),
                    "Accept": "application/json",
                })
                response = connection.getresponse()
                raw = response.read(_MAX_HTTP_RESPONSE_BYTES + 1)
                if len(raw) > _MAX_HTTP_RESPONSE_BYTES:
                    raise network_diagnose.NetworkDiagnoseError("response_too_large")
                if response.status != HTTPStatus.OK:
                    code, upstream_status, upstream_code = _safe_upstream_error(
                        response.status, raw)
                    raise network_diagnose.NetworkDiagnoseError(
                        code, upstream_http_status=upstream_status,
                        upstream_error_code=upstream_code)
                try:
                    value = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise network_diagnose.NetworkDiagnoseError("response_invalid") from None
                if not isinstance(value, dict):
                    raise network_diagnose.NetworkDiagnoseError("response_invalid")
                return value
            except (OSError, http.client.HTTPException):
                raise network_diagnose.NetworkDiagnoseError("connector_unavailable") from None
            finally:
                connection.close()

        try:
            return network_diagnose.run(site_ref, gateway_ref, requester=fixed_read)
        except network_diagnose.NetworkDiagnoseError as exc:
            return {"status": "error", "error": exc.code,
                    "capability_status": "unknown"}

    def _mcp_network_diagnose_switch(self, arguments: dict[str, str]) -> dict[str, object]:
        try:
            from app import switch_diagnose
        except ImportError:
            return {"status": "error", "error": "diagnostic_unavailable"}
        site_ref, switch_ref = arguments["site_ref"], arguments["switch_ref"]
        root = f"/v1/sites/{site_ref}/switches/{switch_ref}"
        allowed_paths = {
            "/v1/sites", f"/v1/sites/{site_ref}/devices",
            root + "/health", root + "/ports", root + "/ports/counters",
            root + "/health/timeline",
            root + "/sdm-usage",
            root + "/cable-test/logs",
            root + "/cable-test/full-results",
            root + "/cable-test/increment-results",
            root + "/cable-test/ports", root + "/dhcp/users", root + "/ospf-neighbors", root + "/port-networks", root + "/exist-networks", root + "/networks", root + "/interfaces", root + "/routing-table", root + "/static-routes",
            root + "/ports/poe-info", root + "/vlans", root + "/lldp-neighbors",
            root + "/vrfs", root + "/vlan-interfaces", root + "/statistics",
        }

        def fixed_read(path: str) -> object:
            if path not in allowed_paths:
                raise switch_diagnose.SwitchDiagnoseError("connector_unavailable")
            connection = http.client.HTTPConnection(
                "127.0.0.1", self.server.server_port, timeout=15)
            try:
                connection.request("GET", path, headers={
                    "Authorization": self.headers.get("Authorization", ""),
                    "Accept": "application/json",
                })
                response = connection.getresponse()
                raw = response.read(_MAX_HTTP_RESPONSE_BYTES + 1)
                if len(raw) > _MAX_HTTP_RESPONSE_BYTES:
                    raise switch_diagnose.SwitchDiagnoseError("response_too_large")
                if response.status != HTTPStatus.OK:
                    raise switch_diagnose.SwitchDiagnoseError("connector_http_error")
                try:
                    value = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise switch_diagnose.SwitchDiagnoseError("response_invalid") from None
                if not isinstance(value, dict):
                    raise switch_diagnose.SwitchDiagnoseError("response_invalid")
                return value
            except (OSError, http.client.HTTPException):
                raise switch_diagnose.SwitchDiagnoseError("connector_unavailable") from None
            finally:
                connection.close()

        try:
            return switch_diagnose.run(site_ref, switch_ref, requester=fixed_read)
        except switch_diagnose.SwitchDiagnoseError as exc:
            return {"status": "error", "error": exc.code,
                    "capability_status": "unknown"}

    def _mcp_network_overview(self, arguments: dict[str, str]) -> dict[str, object]:
        try:
            from app import network_diagnose
        except ImportError:
            return {"status": "error", "error": "diagnostic_unavailable"}
        site_ref = arguments["site_ref"]
        root = f"/v1/sites/{site_ref}"
        allowed_paths = {
            root + "/devices", root + "/health/summary", root + "/networks",
            root + "/dhcp/leases", root + "/dns/cache", root + "/dns/proxy",
            root + "/dns/records",
            root + "/events", root + "/alerts",
            root + "/topology/network-summary",
            root + "/topology/vlan-summary",
            root + "/topology",
        }

        def fixed_read(path: str) -> object:
            if path not in allowed_paths:
                raise network_diagnose.NetworkDiagnoseError("connector_unavailable")
            connection = http.client.HTTPConnection(
                "127.0.0.1", self.server.server_port, timeout=15)
            try:
                connection.request("GET", path, headers={
                    "Authorization": self.headers.get("Authorization", ""),
                    "Accept": "application/json",
                })
                response = connection.getresponse()
                raw = response.read(_MAX_HTTP_RESPONSE_BYTES + 1)
                if len(raw) > _MAX_HTTP_RESPONSE_BYTES:
                    raise network_diagnose.NetworkDiagnoseError("response_too_large")
                if response.status != HTTPStatus.OK:
                    raise network_diagnose.NetworkDiagnoseError("connector_http_error")
                try:
                    value = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise network_diagnose.NetworkDiagnoseError("response_invalid") from None
                if not isinstance(value, dict):
                    raise network_diagnose.NetworkDiagnoseError("response_invalid")
                return value
            except (OSError, http.client.HTTPException):
                raise network_diagnose.NetworkDiagnoseError("connector_unavailable") from None
            finally:
                connection.close()

        try:
            return network_diagnose.run_site(site_ref, requester=fixed_read)
        except network_diagnose.NetworkDiagnoseError as exc:
            return {"status": "error", "error": exc.code,
                    "capability_status": "unknown"}

    def _mcp_ssid_network_summary(self, arguments: dict[str, str]) -> dict[str, object]:
        try:
            from app import ssid_network_diagnose
        except ImportError:
            return {"status": "error", "error": "diagnostic_unavailable"}
        site_ref = arguments["site_ref"]
        root = f"/v1/sites/{site_ref}"
        allowed_paths = {"/v1/sites", root + "/ssids", root + "/networks",
                         root + "/devices", root + "/dns/cache", root + "/dns/proxy"}

        def fixed_read(path: str) -> object:
            patterns = (
                rf"{re.escape(root)}/ssids/[0-9a-f]{{24}}",
                rf"{re.escape(root)}/lan-networks/[0-9a-f]{{24}}/summary",
                rf"{re.escape(root)}/networks/[0-9a-f]{{24}}/dhcp-server/info",
                rf"{re.escape(root)}/gateways/[0-9a-f]{{24}}/internet-info",
            )
            if path not in allowed_paths and not any(re.fullmatch(pattern, path) for pattern in patterns):
                raise ssid_network_diagnose.SsidNetworkDiagnoseError("connector_unavailable")
            connection = http.client.HTTPConnection(
                "127.0.0.1", self.server.server_port, timeout=15)
            try:
                connection.request("GET", path, headers={
                    "Authorization": self.headers.get("Authorization", ""),
                    "Accept": "application/json",
                })
                response = connection.getresponse()
                raw = response.read(_MAX_HTTP_RESPONSE_BYTES + 1)
                if len(raw) > _MAX_HTTP_RESPONSE_BYTES:
                    raise ssid_network_diagnose.SsidNetworkDiagnoseError("response_too_large")
                if response.status != HTTPStatus.OK:
                    raise ssid_network_diagnose.SsidNetworkDiagnoseError("connector_http_error")
                try:
                    value = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise ssid_network_diagnose.SsidNetworkDiagnoseError("response_invalid") from None
                if not isinstance(value, dict):
                    raise ssid_network_diagnose.SsidNetworkDiagnoseError("response_invalid")
                return value
            except (OSError, http.client.HTTPException):
                raise ssid_network_diagnose.SsidNetworkDiagnoseError(
                    "connector_unavailable") from None
            finally:
                connection.close()

        try:
            return ssid_network_diagnose.run_site(site_ref, requester=fixed_read)
        except ssid_network_diagnose.SsidNetworkDiagnoseError as exc:
            return {"status": "error", "error": exc.code,
                    "capability_status": "unknown"}

    def _authorized(self) -> bool:
        configured = _caller_token()
        if configured is None:
            self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "error": "route_disabled"})
            return False
        authorization = self.headers.get("Authorization", "")
        scheme, separator, supplied = authorization.partition(" ")
        try:
            supplied_bytes = supplied.encode("ascii") if separator and scheme.lower() == "bearer" and len(supplied) <= 4096 else b""
        except UnicodeEncodeError:
            supplied_bytes = b""
        if not hmac.compare_digest(configured, supplied_bytes):
            self._send(HTTPStatus.UNAUTHORIZED, {"status": "error", "error": "unauthorized"})
            return False
        return True

    def _serve_site_outage_summary(self, parsed_request: object, match: object) -> None:
        if not self._authorized():
            return
        try:
            query_values = parse_qs(parsed_request.query, keep_blank_values=True,
                                    strict_parsing=True)
            if (set(query_values) != {"start_ms", "end_ms"} or
                    any(len(values) != 1 for values in query_values.values())):
                raise RegistryError("outage summary requires one start_ms and end_ms")
            start_text, end_text = query_values["start_ms"][0], query_values["end_ms"][0]
            if (not re.fullmatch(r"[0-9]{12,13}", start_text) or
                    not re.fullmatch(r"[0-9]{12,13}", end_text)):
                raise RegistryError("outage summary time bounds invalid")
            with _OPENAPI_LOCK:
                result = _openapi_client().read_site_outage_summary(
                    match.group(1), int(start_text), int(end_text))
            self._send(HTTPStatus.OK, result)
        except RegistryError:
            self._send(HTTPStatus.BAD_REQUEST,
                       {"status": "error", "error": "query_invalid"})
        except OpenApiError as exc:
            status = (HTTPStatus.BAD_REQUEST if exc.args and exc.args[0] in {
                "site_ref_invalid", "site_ref_unknown", "time_window_invalid"}
                else HTTPStatus.BAD_GATEWAY)
            self._send(status, {"status": "error", "error": str(exc)})

    def _serve_site_capability_comparison(self, parsed_request: object) -> None:
        if not self._authorized():
            return
        try:
            query_values = parse_qs(parsed_request.query, keep_blank_values=True,
                                    strict_parsing=True)
            refs = query_values.get("site_ref", [])
            if set(query_values) != {"site_ref"} or not 2 <= len(refs) <= 16:
                raise RegistryError("site refs invalid")
            with _OPENAPI_LOCK:
                result = _openapi_client().read_site_capability_comparison(refs)
            self._send(HTTPStatus.OK, result)
        except (RegistryError, ValueError):
            self._send(HTTPStatus.BAD_REQUEST,
                       {"status": "error", "error": "site_refs_invalid"})
        except OpenApiError as exc:
            status = (HTTPStatus.BAD_REQUEST if exc.code == "site_refs_invalid"
                      else HTTPStatus.BAD_GATEWAY)
            self._send(status, {"status": "error", "error": exc.code})

    def _serve_site_client_outage_overlap(self, parsed_request: object, match: object) -> None:
        if not self._authorized():
            return
        try:
            query_values = parse_qs(parsed_request.query, keep_blank_values=True,
                                    strict_parsing=True)
            if (set(query_values) != {"start_ms", "end_ms", "client_ref"} or
                    len(query_values.get("start_ms", [])) != 1 or
                    len(query_values.get("end_ms", [])) != 1 or
                    not 2 <= len(query_values.get("client_ref", [])) <= 16):
                raise RegistryError("client outage overlap query invalid")
            client_refs = query_values["client_ref"]
            if (any(not re.fullmatch(r"[0-9a-f]{24}", ref) for ref in client_refs) or
                    len(set(client_refs)) != len(client_refs)):
                raise RegistryError("client outage overlap client refs invalid")
            start_text, end_text = query_values["start_ms"][0], query_values["end_ms"][0]
            if (not re.fullmatch(r"[0-9]{12,13}", start_text) or
                    not re.fullmatch(r"[0-9]{12,13}", end_text)):
                raise RegistryError("client outage overlap time bounds invalid")
            with _OPENAPI_LOCK:
                result = _openapi_client().read_site_client_outage_overlap_summary(
                    match.group(1), client_refs, int(start_text), int(end_text))
            self._send(HTTPStatus.OK, result)
        except RegistryError:
            self._send(HTTPStatus.BAD_REQUEST,
                       {"status": "error", "error": "query_invalid"})
        except OpenApiError as exc:
            status = (HTTPStatus.BAD_REQUEST if exc.code in {
                "client_refs_invalid", "time_window_invalid", "site_ref_invalid"} else
                HTTPStatus.NOT_FOUND if exc.code in {"site_ref_unknown", "client_ref_unknown"} else
                HTTPStatus.BAD_GATEWAY)
            self._send(status, {"status": "error", "error": exc.code})

    def _serve_site_client_roaming_backtrack(self, parsed_request: object,
                                             match: object) -> None:
        if not self._authorized():
            return
        try:
            query_values = parse_qs(parsed_request.query, keep_blank_values=True,
                                    strict_parsing=True)
            if (set(query_values) != {"start_ms", "end_ms", "client_ref"} or
                    len(query_values.get("start_ms", [])) != 1 or
                    len(query_values.get("end_ms", [])) != 1 or
                    not 1 <= len(query_values.get("client_ref", [])) <= 16):
                raise RegistryError("client roaming query invalid")
            client_refs = query_values["client_ref"]
            if (any(not re.fullmatch(r"[0-9a-f]{24}", ref) for ref in client_refs) or
                    len(set(client_refs)) != len(client_refs)):
                raise RegistryError("client roaming refs invalid")
            start_text, end_text = query_values["start_ms"][0], query_values["end_ms"][0]
            if (not re.fullmatch(r"[0-9]{12,13}", start_text) or
                    not re.fullmatch(r"[0-9]{12,13}", end_text)):
                raise RegistryError("client roaming time bounds invalid")
            with _OPENAPI_LOCK:
                result = _openapi_client().read_site_client_roaming_backtrack_summary(
                    match.group(1), client_refs, int(start_text), int(end_text))
            self._send(HTTPStatus.OK, result)
        except RegistryError:
            self._send(HTTPStatus.BAD_REQUEST,
                       {"status": "error", "error": "query_invalid"})
        except OpenApiError as exc:
            status = (HTTPStatus.BAD_REQUEST if exc.code in {
                "client_refs_invalid", "time_window_invalid", "site_ref_invalid"} else
                HTTPStatus.NOT_FOUND if exc.code in {"site_ref_unknown", "client_ref_unknown"} else
                HTTPStatus.BAD_GATEWAY)
            self._send(status, {"status": "error", "error": exc.code})

    def _serve_site_ap_uplink_path(self, parsed_request: object, match: object) -> None:
        if not self._authorized():
            return
        try:
            query_values = parse_qs(parsed_request.query, keep_blank_values=True,
                                    strict_parsing=True)
            refs = query_values.get("device_ref", [])
            if (set(query_values) != {"device_ref"} or not 1 <= len(refs) <= 16 or
                    any(not re.fullmatch(r"[0-9a-f]{24}", ref) for ref in refs) or
                    len(set(refs)) != len(refs)):
                raise RegistryError("AP uplink path query invalid")
            with _OPENAPI_LOCK:
                result = _openapi_client().read_site_ap_uplink_path_summary(
                    match.group(1), refs)
            self._send(HTTPStatus.OK, result)
        except RegistryError:
            self._send(HTTPStatus.BAD_REQUEST,
                       {"status": "error", "error": "query_invalid"})
        except OpenApiError as exc:
            status = (HTTPStatus.BAD_REQUEST if exc.code in {
                "device_refs_invalid", "site_ref_invalid"} else
                HTTPStatus.NOT_FOUND if exc.code in {
                    "site_ref_unknown", "device_ref_unknown"} else
                HTTPStatus.BAD_GATEWAY)
            self._send(status, {"status": "error", "error": exc.code})

    def _serve_site_channel_reuse(self, parsed_request: object, site_ref: str) -> None:
        if not self._authorized():
            return
        try:
            query_values = parse_qs(parsed_request.query, keep_blank_values=True,
                                    strict_parsing=True)
            if set(query_values) != {"device_refs"} or len(query_values["device_refs"]) != 1:
                raise RegistryError("device refs invalid")
            device_refs = query_values["device_refs"][0].split(",")
            if (not 1 <= len(device_refs) <= 16 or
                    any(not re.fullmatch(r"[0-9a-f]{24}", ref) for ref in device_refs) or
                    len(set(device_refs)) != len(device_refs)):
                raise RegistryError("device refs invalid")
            with _OPENAPI_LOCK:
                result = _openapi_client().read_site_channel_reuse_summary(site_ref, device_refs)
            self._send(HTTPStatus.OK, result)
        except RegistryError:
            self._send(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "query_invalid"})
        except OpenApiError as exc:
            status = (HTTPStatus.BAD_REQUEST if exc.code in {"site_ref_invalid", "device_refs_invalid"}
                      else HTTPStatus.NOT_FOUND if exc.code in {"site_ref_unknown", "device_ref_unknown"}
                      else HTTPStatus.BAD_GATEWAY)
            self._send(status, {"status": "error", "error": exc.code})

    def _serve_gateway_wan_incident_window(self, parsed_request: object,
                                           match: object) -> None:
        if not self._authorized():
            return
        try:
            query_values = parse_qs(parsed_request.query, keep_blank_values=True,
                                    strict_parsing=True)
            if (set(query_values) != {"start_ms", "end_ms"} or
                    any(len(values) != 1 for values in query_values.values())):
                raise RegistryError("window arguments invalid")
            start_text, end_text = query_values["start_ms"][0], query_values["end_ms"][0]
            if (not re.fullmatch(r"[0-9]{12,13}", start_text) or
                    not re.fullmatch(r"[0-9]{12,13}", end_text)):
                raise RegistryError("window arguments invalid")
            with _OPENAPI_LOCK:
                result = _openapi_client().read_gateway_wan_incident_window(
                    match.group(1), match.group(2), int(start_text), int(end_text))
            self._send(HTTPStatus.OK, result)
        except RegistryError:
            self._send(HTTPStatus.BAD_REQUEST,
                       {"status": "error", "error": "query_invalid"})
        except OpenApiError as exc:
            status = (HTTPStatus.BAD_REQUEST if exc.code in {
                "site_ref_invalid", "site_ref_unknown", "device_ref_invalid",
                "device_ref_unknown", "gateway_health_time_window_invalid"}
                else HTTPStatus.BAD_GATEWAY)
            self._send(status, {"status": "error", "error": exc.code})

    def _serve_site_dhcp_pool_utilization(self, site_ref: str) -> None:
        if not self._authorized():
            return
        try:
            with _OPENAPI_LOCK:
                result = _openapi_client().read_site_dhcp_pool_utilization(site_ref)
            self._send(HTTPStatus.OK, result)
        except OpenApiError as exc:
            status = (HTTPStatus.BAD_REQUEST if exc.code in {
                "site_ref_invalid", "site_ref_unknown"} else HTTPStatus.BAD_GATEWAY)
            self._send(status, {"status": "error", "error": exc.code})

    def _serve_site_ap_quality_window(self, site_ref: str) -> None:
        if not self._authorized():
            return
        try:
            with _OPENAPI_LOCK:
                result = _openapi_client().read_site_ap_quality_window(site_ref)
            self._send(HTTPStatus.OK, result)
        except OpenApiError as exc:
            status = (HTTPStatus.BAD_REQUEST if exc.code in {
                "site_ref_invalid", "site_ref_unknown"} else HTTPStatus.BAD_GATEWAY)
            self._send(status, {"status": "error", "error": exc.code})

    def _serve_site_switch_health_history(self, site_ref: str) -> None:
        if not self._authorized():
            return
        try:
            with _OPENAPI_LOCK:
                result = _openapi_client().read_site_switch_health_history(site_ref)
            self._send(HTTPStatus.OK, result)
        except OpenApiError as exc:
            status = (HTTPStatus.BAD_REQUEST if exc.code in {
                "site_ref_invalid", "site_ref_unknown"} else HTTPStatus.BAD_GATEWAY)
            self._send(status, {"status": "error", "error": exc.code})

    def _serve_site_firmware_summary(self, site_ref: str) -> None:
        if not self._authorized():
            return
        try:
            with _OPENAPI_LOCK:
                result = _openapi_client().read_site_firmware_summary(site_ref)
            self._send(HTTPStatus.OK, result)
        except OpenApiError as exc:
            status = (HTTPStatus.BAD_REQUEST if exc.code in {
                "site_ref_invalid", "site_ref_unknown"} else HTTPStatus.BAD_GATEWAY)
            self._send(status, {"status": "error", "error": exc.code})

    def _serve_site_switch_port_anomaly_summary(self, site_ref: str) -> None:
        if not self._authorized():
            return
        try:
            with _OPENAPI_LOCK:
                result = _openapi_client().read_site_switch_port_anomaly_summary(site_ref)
            self._send(HTTPStatus.OK, result)
        except OpenApiError as exc:
            status = (HTTPStatus.BAD_REQUEST if exc.code in {
                "site_ref_invalid", "site_ref_unknown"} else HTTPStatus.BAD_GATEWAY)
            self._send(status, {"status": "error", "error": exc.code})

    def _openapi_get(self) -> None:
        registry_match = None
        try:
            parsed_request = urlsplit(self.path)
            if parsed_request.path == "/v1/sites/capability-comparison":
                self._serve_site_capability_comparison(parsed_request)
                return
            client_overlap_match = re.fullmatch(
                r"/v1/sites/([0-9a-f]{24})/client-outage-overlaps", parsed_request.path)
            if client_overlap_match is not None:
                self._serve_site_client_outage_overlap(parsed_request, client_overlap_match)
                return
            client_roaming_match = re.fullmatch(
                r"/v1/sites/([0-9a-f]{24})/client-roaming-backtracks", parsed_request.path)
            if client_roaming_match is not None:
                self._serve_site_client_roaming_backtrack(parsed_request, client_roaming_match)
                return
            ap_uplink_path_match = re.fullmatch(
                r"/v1/sites/([0-9a-f]{24})/ap-uplink-paths", parsed_request.path)
            if ap_uplink_path_match is not None:
                self._serve_site_ap_uplink_path(parsed_request, ap_uplink_path_match)
                return
            channel_reuse_match = re.fullmatch(
                r"/v1/sites/([0-9a-f]{24})/channel-reuse", parsed_request.path)
            if channel_reuse_match is not None:
                self._serve_site_channel_reuse(parsed_request, channel_reuse_match.group(1))
                return
            outage_match = re.fullmatch(
                r"/v1/sites/([0-9a-f]{24})/outage-summary", parsed_request.path)
            if outage_match is not None:
                self._serve_site_outage_summary(parsed_request, outage_match)
                return
            wan_window_match = re.fullmatch(
                r"/v1/sites/([0-9a-f]{24})/gateways/([0-9a-f]{24})/wan-incident-window",
                parsed_request.path)
            if wan_window_match is not None:
                self._serve_gateway_wan_incident_window(parsed_request, wan_window_match)
                return
            dhcp_pool_match = re.fullmatch(
                r"/v1/sites/([0-9a-f]{24})/dhcp/pool-utilization", parsed_request.path)
            if dhcp_pool_match is not None:
                self._serve_site_dhcp_pool_utilization(dhcp_pool_match.group(1))
                return
            ap_quality_match = re.fullmatch(
                r"/v1/sites/([0-9a-f]{24})/aps/quality-window", parsed_request.path)
            if ap_quality_match is not None:
                self._serve_site_ap_quality_window(ap_quality_match.group(1))
                return
            switch_health_history_match = re.fullmatch(
                r"/v1/sites/([0-9a-f]{24})/switches/health-history", parsed_request.path)
            if switch_health_history_match is not None:
                self._serve_site_switch_health_history(
                    switch_health_history_match.group(1))
                return
            firmware_summary_match = re.fullmatch(
                r"/v1/sites/([0-9a-f]{24})/firmware-summary", parsed_request.path)
            if firmware_summary_match is not None:
                self._serve_site_firmware_summary(firmware_summary_match.group(1))
                return
            switch_port_anomaly_match = re.fullmatch(
                r"/v1/sites/([0-9a-f]{24})/switches/port-anomalies", parsed_request.path)
            if switch_port_anomaly_match is not None:
                self._serve_site_switch_port_anomaly_summary(switch_port_anomaly_match.group(1))
                return
            registry_match = REGISTRY.match("GET", parsed_request.path)
            operation = registry_match[0]
            query_values = parse_qs(parsed_request.query, keep_blank_values=True, strict_parsing=True)
            local_argument_sets = REGISTRY.local_argument_sets(operation)
            optional_argument_sets = {
                frozenset(group)
                for size in range(len(operation.optional_arguments) + 1)
                for group in itertools.combinations(operation.optional_arguments, size)
            }
            allowed_query_sets = {
                frozenset(operation.extra_arguments) | frozenset(group) | optional
                for group in local_argument_sets
                for optional in optional_argument_sets
            }
            if (frozenset(query_values) not in allowed_query_sets or
                    any(len(values) != 1 for values in query_values.values())):
                raise RegistryError("query not allowed")
            local_arguments = set(query_values) - set(operation.extra_arguments)
            registry_bindings = dict(registry_match[1])
            registry_bindings.update({name: values[0] for name, values in query_values.items()})
            if "function" in operation.extra_arguments:
                function_text = registry_bindings["function"]
                if not re.fullmatch(r"(?:0|[1-9]|1[0-5])", function_text):
                    raise RegistryError("wan function invalid")
            if ("interface_type" in operation.optional_arguments and
                    registry_bindings.get("interface_type") not in {None, "0"}):
                raise RegistryError("interface type invalid")
            for name in {"client_name", "ssid_name"} & local_arguments:
                value = registry_bindings[name]
                if (not 1 <= len(value) <= 128 or value != value.strip() or
                        any(ord(char) < 32 or ord(char) == 127 for char in value)):
                    raise RegistryError("client identity input invalid")
            if {"start_ms", "end_ms"}.issubset(local_arguments):
                start_text, end_text = registry_bindings["start_ms"], registry_bindings["end_ms"]
                if (not re.fullmatch(r"[0-9]{12,13}", start_text) or
                        not re.fullmatch(r"[0-9]{12,13}", end_text)):
                    raise RegistryError("log time bound invalid")
                start_ms, end_ms = int(start_text), int(end_text)
                now_ms = int(time.time() * 1000)
                if (not 946684800000 <= start_ms <= end_ms <= 4102444800000 or
                        end_ms - start_ms > 86_400_000 or end_ms > now_ms + 60_000):
                    raise RegistryError("log time window invalid")
            if {"start_local", "end_local", "time_zone"} == local_arguments:
                try:
                    resolve_local_site_log_window(
                        registry_bindings["start_local"], registry_bindings["end_local"],
                        registry_bindings["time_zone"], int(time.time() * 1000))
                except SiteLogWindowError as exc:
                    raise RegistryError("local log time window invalid") from exc
            if "archived" in local_arguments and registry_bindings.get("archived") not in {"true", "false"}:
                raise RegistryError("archived selector invalid")
            if "vlan_id" in local_arguments:
                vlan_text = registry_bindings["vlan_id"]
                if (not re.fullmatch(r"[1-9][0-9]{0,3}", vlan_text) or
                        not 1 <= int(vlan_text) <= 4094):
                    raise RegistryError("vlan selector invalid")
            if "pon_port" in registry_bindings:
                validate_pon_port_selector(registry_bindings["pon_port"])
            if "page_number" in registry_bindings:
                number, size = registry_bindings["page_number"], registry_bindings["page_size"]
                min_page = 1 if operation.operation_id == "controller_upgrade_log_inventory" else 0
                max_page = 10 if operation.operation_id == "controller_upgrade_log_inventory" else 10_000
                if (not number.isdecimal() or not size.isdecimal() or
                        str(int(number)) != number or str(int(size)) != size or
                        not min_page <= int(number) <= max_page or not 1 <= int(size) <= 100):
                    raise RegistryError("page arguments invalid")
            if "vpn_type" in registry_bindings:
                allowed_vpn_types = (
                    {"2", "4"} if operation.operation_id == "site_vpn_s2s_status_summary"
                    else set("012345") if operation.operation_id == "site_vpn_server_status_summary"
                    else {"0", "1", "3", "4"} if operation.operation_id == "site_vpn_client_status_summary"
                    else {"0", "1"})
                if registry_bindings["vpn_type"] not in allowed_vpn_types:
                    raise RegistryError("vpn type invalid")
            if (operation.operation_id == "site_routing_table_summary" and
                    registry_bindings.get("device_type") not in {"gateway", "switch"}):
                raise RegistryError("device type invalid")
            if (operation.operation_id == "site_mac_auth_ssid_inventory" and
                    registry_bindings.get("type") not in {"1", "2", "3"}):
                raise RegistryError("device type invalid")
        except OltOnuInventoryError:
            self._send(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "pon_port_invalid"})
            return
        except (RegistryError, ValueError):
            if (registry_match and
                    registry_match[0].operation_id in {"site_mac_auth_ssid_inventory", "site_vlan_ssid_usage_summary",
                                                        "site_vlan_device_usage_summary", "site_vlan_port_support_summary", "site_vlan_topology_summary", "site_vlan_topology_reference_count",
                                                        "site_lan_network_interface_summary", "controller_upgrade_log_inventory"}):
                self._send(HTTPStatus.BAD_REQUEST,
                           {"status": "error", "error": "query_invalid"})
                return
            registry_match = None
            registry_bindings = {}
        registry_operation = registry_match[0].operation_id if registry_match else None
        sites_route = registry_operation == "sites"
        controller_health_match = registry_operation == "controller_health"
        controller_gateway_wan_status_match = registry_operation == "controller_gateway_wan_status_summary"
        controller_sdwan_group_summary_match = (
            registry_match if registry_operation == "controller_sdwan_group_summary" else None)
        site_overview_match = registry_match if registry_operation == "site_overview" else None
        site_topology_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/topology", self.path)
        site_health_timeline_match = registry_match if registry_operation == "site_health_timeline" else None
        site_client_health_timeline_match = (
            registry_match if registry_operation == "site_client_health_timeline" else None)
        site_wifi_summary_match = (
            registry_match if registry_operation == "site_wifi_summary" else None)
        site_6ghz_ap_presence_match = (
            registry_match if registry_operation == "site_6ghz_ap_presence" else None)
        site_setting_existence_match = (
            registry_match if registry_operation == "site_setting_existence" else None)
        site_capabilities_match = (
            registry_match if registry_operation == "site_capabilities" else None)
        site_rogue_ap_results_match = (
            registry_match if registry_operation == "site_rogue_ap_results" else None)
        site_wids_summary_match = (
            registry_match if registry_operation == "site_wids_summary" else None)
        site_wids_blacklist_summary_match = (
            registry_match if registry_operation == "site_wids_blacklist_summary" else None)
        switch_port_tags_match = (
            registry_match if registry_operation == "switch_port_tags" else None)
        ap_wifi_neighbors_match = (
            registry_match if registry_operation == "ap_wifi_interference" else None)
        ap_speed_test_results_match = (
            registry_match if registry_operation == "ap_speed_test_results" else None)
        ap_wired_downlink_match = (
            registry_match if registry_operation == "ap_wired_downlink" else None)
        ap_ports_match = registry_match if registry_operation == "ap_ports" else None
        ap_uplink_config_match = (
            registry_match if registry_operation == "ap_uplink_config" else None)
        ap_lldp_config_match = (
            registry_match if registry_operation == "ap_lldp_config" else None)
        ap_port_vlans_match = (
            registry_match if registry_operation == "ap_port_vlans" else None)
        ap_bridge_config_match = (
            registry_match if registry_operation == "ap_bridge_config" else None)
        ap_mesh_candidates_match = (
            registry_match if registry_operation == "ap_mesh_candidates" else None)
        ap_general_config_match = (
            registry_match if registry_operation == "ap_general_config" else None)
        ap_ip_setting_match = (
            registry_match if registry_operation == "ap_ip_setting" else None)
        ap_ipv6_setting_match = (
            registry_match if registry_operation == "ap_ipv6_setting" else None)
        ap_p2p_info_match = (
            registry_match if registry_operation == "ap_p2p_info" else None)
        ap_l3_access_match = (
            registry_match if registry_operation == "ap_l3_access" else None)
        ap_paring_window_match = (
            registry_match if registry_operation == "ap_paring_window" else None)
        ap_lag_config_match = (
            registry_match if registry_operation == "ap_lag_config" else None)
        ap_rf_scan_v2_match = (
            registry_match if registry_operation == "ap_rf_scan_v2" else None)
        ap_management_ssid_match = (
            registry_match if registry_operation == "ap_management_ssid" else None)
        ap_snmp_config_match = (
            registry_match if registry_operation == "ap_snmp_config" else None)
        ap_vlan_v1_match = (
            registry_match if registry_operation == "ap_vlan_v1" else None)
        ap_wlan_overrides_match = (
            registry_match if registry_operation == "ap_wlan_overrides" else None)
        experience_index_match = (
            registry_match if registry_operation == "experience_index" else None)
        rf_planning_result_match = (
            registry_match if registry_operation == "rf_planning_result" else None)
        rf_planning_dashboard_match = (
            registry_match if registry_operation == "rf_planning_dashboard" else None)
        rf_planning_dashboard_current_match = (
            registry_match if registry_operation == "rf_planning_dashboard_current" else None)
        rf_planning_dashboard_history_match = (
            registry_match if registry_operation == "rf_planning_dashboard_history" else None)
        rf_planning_detail_match = (
            registry_match if registry_operation == "rf_planning_detail" else None)
        rf_planning_history_match = (
            registry_match if registry_operation == "rf_planning_history" else None)
        rf_planning_history_detail_match = (
            registry_match if registry_operation == "rf_planning_history_detail" else None)
        rf_planning_recent_history_match = (
            registry_match if registry_operation == "rf_planning_recent_history" else None)
        rf_excluded_aps_match = (
            registry_match if registry_operation == "rf_excluded_aps" else None)
        rf_deploy_history_match = (
            registry_match if registry_operation == "rf_deploy_history" else None)
        wifi_health_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/wifi/health/timeline", self.path)
        wifi_health_details_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/wifi/health/details", self.path)
        band_steering_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/wifi/band-steering", self.path)
        rrm_settings_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/wifi/optimization", self.path)
        roaming_settings_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/wifi/roaming", self.path)
        rrm_incompatible_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/wifi/rrm-incompatible", self.path)
        site_dashboard_channels_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/wifi/channels", self.path)
        site_client_signal_distribution_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/wifi/client-signal-distribution", self.path)
        site_led_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/led", self.path)
        site_lldp_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/lldp", self.path)
        site_dpi_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/application-control", self.path)
        gateway_voip_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/qos/gateway/voip-prioritization", self.path)
        gateway_tag_qos_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/qos/gateway/tag-outbound-traffic", self.path)
        site_channel_limit_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/wifi/channel-limit", self.path)
        ap_channel_limit_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/channel-limit", self.path)
        ap_ofdma_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/ofdma", self.path)
        ap_qos_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/qos", self.path)
        ap_lag_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/lag", self.path)
        ap_load_balance_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/load-balance", self.path)
        ap_antenna_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/antenna", self.path)
        ap_antenna_gain_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/antenna-gain", self.path)
        ap_power_saving_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/power-saving", self.path)
        ap_wired_uplink_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/wired-uplink", self.path)
        ap_lan_traffic_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/lan-traffic", self.path)
        ap_vlan_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/vlan", self.path)
        devices_match = registry_match if registry_operation == "devices" else None
        device_firmware_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/devices/([0-9a-f]{24})/firmware", self.path)
        ap_health_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/health", self.path)
        ap_health_timeline_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/health/timeline", self.path)
        ap_afc_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/afc", self.path)
        ap_afc_status_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/afc/status", self.path)
        ap_retry_drop_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/aps/retry-drop", self.path)
        ap_mesh_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/mesh", self.path)
        clients_match = registry_match if registry_operation == "clients" else None
        recent_clients_match = (registry_match if registry_operation == "site_recent_clients_summary" else None)
        client_detail_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/clients/([0-9a-f]{24})", self.path)
        client_connections_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/clients/([0-9a-f]{24})/connections", self.path)
        client_history_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/clients/([0-9a-f]{24})/history", self.path)
        client_timeline_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/clients/([0-9a-f]{24})/timeline/(connect|association|roaming|disconnect|blocked)",
            self.path)
        client_health_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/clients/([0-9a-f]{24})/health", self.path)
        client_health_detail_v2_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/clients/([0-9a-f]{24})/health/detail-v2", self.path)
        client_health_timeline_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/clients/([0-9a-f]{24})/health/timeline", self.path)
        networks_match = registry_match if registry_operation == "networks" else None
        ssids_match = registry_match if registry_operation == "ssids" else None
        ap_available_channels_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/available-channels", self.path)
        wlan_groups_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/wireless-groups", self.path)
        ssid_config_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/ssids/([0-9a-f]{24})", self.path)
        ap_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/(radio-config|radios|scan-status|channel-load)",
            self.path,
        )
        ap_rf_scan_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/aps/([0-9a-f]{24})/rf-scan", self.path)
        gateway_wan_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/gateways/([0-9a-f]{24})/wan-status", self.path)
        gateway_wan_health_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/gateways/([0-9a-f]{24})/wan-health", self.path)
        gateway_health_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/gateways/([0-9a-f]{24})/health", self.path)
        gateway_health_timeline_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/gateways/([0-9a-f]{24})/health/timeline", self.path)
        gateway_lan_status_match = (
            registry_match if registry_operation == "gateway_lan_status" else None)
        gateway_ports_match = (
            registry_match if registry_operation == "gateway_ports" else None)
        gateway_speed_test_results_match = (
            registry_match if registry_operation == "gateway_speed_test_results" else None)
        site_speed_test_settings_match = (
            registry_match if registry_operation == "site_speed_test_settings" else None)
        gateway_dhcp_leases_match = (
            registry_match if registry_operation == "gateway_dhcp_leases" else None)
        gateway_internet_info_match = (
            registry_match if registry_operation == "gateway_internet_info" else None)
        gateway_ipv6_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/gateways/([0-9a-f]{24})/ipv6-ip-passthrough",
            self.path)
        switch_poe_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/ports/([0-9]{1,5})/poe",
            self.path)
        switch_port_status_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/ports/([0-9]{1,5})/status",
            self.path)
        switch_ports_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/ports", self.path)
        switch_port_counters_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/ports/counters", self.path)
        switch_port_poe_info_match = re.fullmatch(
            r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/ports/poe-info", self.path)
        switch_vlans_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/vlans", self.path)
        switch_lldp_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/lldp-neighbors", self.path)
        switch_health_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/health", self.path)
        switch_health_timeline_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/health/timeline", self.path)
        switch_sdm_usage_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/sdm-usage", self.path)
        switch_cable_test_logs_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/cable-test/logs", self.path)
        switch_cable_test_full_results_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/cable-test/full-results", self.path)
        switch_cable_test_increment_results_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/cable-test/increment-results", self.path)
        switch_cable_test_ports_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/cable-test/ports", self.path)
        switch_dhcp_users_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/dhcp/users", self.path)
        switch_ospf_neighbors_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/ospf-neighbors", self.path)
        switch_port_networks_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/port-networks", self.path)
        switch_exist_networks_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/exist-networks", self.path)
        switch_networks_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/networks", self.path)
        switch_interfaces_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/interfaces", self.path)
        switch_routing_table_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/routing-table", self.path)
        switch_static_routes_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/static-routes", self.path)
        switch_vrfs_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/vrfs", self.path)
        switch_vlan_interfaces_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/vlan-interfaces", self.path)
        switch_statistics_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/switches/([0-9a-f]{24})/statistics", self.path)
        firewall_rules_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/firewall/gateway-acls", self.path)
        switch_acl_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/firewall/switch-acls", self.path)
        ap_acl_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/firewall/ap-acls", self.path)
        dhcp_leases_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/dhcp/leases", self.path)
        dns_cache_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/dns/cache", self.path)
        dns_proxy_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/dns/proxy", self.path)
        dns_records_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/dns/records", self.path)
        events_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/events", self.path)
        alerts_match = re.fullmatch(r"/v1/sites/([0-9a-f]{24})/alerts", self.path)
        if registry_match is None and site_channel_limit_match is None and ap_channel_limit_match is None and ap_ofdma_match is None and ap_qos_match is None and ap_lag_match is None and ap_load_balance_match is None and ap_antenna_match is None and ap_antenna_gain_match is None and ap_power_saving_match is None and ap_wired_uplink_match is None and ap_wired_downlink_match is None and ap_ports_match is None and ap_lan_traffic_match is None and ap_vlan_match is None and site_lldp_match is None and site_dpi_match is None and gateway_voip_match is None and gateway_tag_qos_match is None and ap_afc_status_match is None and ap_afc_match is None and site_led_match is None and roaming_settings_match is None and rrm_incompatible_match is None and site_dashboard_channels_match is None and site_client_signal_distribution_match is None and band_steering_match is None and rrm_settings_match is None and switch_port_status_match is None and switch_health_match is None and switch_health_timeline_match is None and switch_sdm_usage_match is None and switch_cable_test_logs_match is None and switch_cable_test_full_results_match is None and switch_cable_test_increment_results_match is None and switch_cable_test_ports_match is None and switch_dhcp_users_match is None and switch_ospf_neighbors_match is None and switch_port_networks_match is None and switch_exist_networks_match is None and switch_networks_match is None and switch_interfaces_match is None and switch_routing_table_match is None and switch_static_routes_match is None and switch_vrfs_match is None and switch_vlan_interfaces_match is None and switch_statistics_match is None and switch_lldp_match is None and wifi_health_match is None and wifi_health_details_match is None and not sites_route and not controller_health_match and not controller_gateway_wan_status_match and controller_sdwan_group_summary_match is None and site_overview_match is None and site_topology_match is None and site_health_timeline_match is None and site_client_health_timeline_match is None and site_wifi_summary_match is None and site_6ghz_ap_presence_match is None and site_setting_existence_match is None and site_capabilities_match is None and site_rogue_ap_results_match is None and site_wids_summary_match is None and site_wids_blacklist_summary_match is None and switch_port_tags_match is None and ap_wifi_neighbors_match is None and ap_speed_test_results_match is None and experience_index_match is None and rf_planning_result_match is None and rf_planning_dashboard_match is None and rf_planning_dashboard_history_match is None and rf_planning_dashboard_current_match is None and rf_planning_detail_match is None and rf_planning_history_match is None and rf_planning_history_detail_match is None and rf_planning_recent_history_match is None and rf_excluded_aps_match is None and rf_deploy_history_match is None and devices_match is None and device_firmware_match is None and ap_health_match is None and ap_health_timeline_match is None and ap_retry_drop_match is None and ap_mesh_match is None and clients_match is None and recent_clients_match is None and client_detail_match is None and client_connections_match is None and client_history_match is None and client_timeline_match is None and client_health_match is None and client_health_detail_v2_match is None and client_health_timeline_match is None and networks_match is None and ssids_match is None and wlan_groups_match is None and ssid_config_match is None and ap_available_channels_match is None and ap_match is None and ap_rf_scan_match is None and gateway_wan_match is None and gateway_wan_health_match is None and gateway_health_match is None and gateway_health_timeline_match is None and gateway_lan_status_match is None and gateway_ports_match is None and gateway_speed_test_results_match is None and gateway_dhcp_leases_match is None and gateway_internet_info_match is None and gateway_ipv6_match is None and switch_ports_match is None and switch_port_counters_match is None and switch_port_poe_info_match is None and switch_poe_match is None and switch_vlans_match is None and firewall_rules_match is None and switch_acl_match is None and ap_acl_match is None and dhcp_leases_match is None and dns_cache_match is None and dns_proxy_match is None and dns_records_match is None and events_match is None and alerts_match is None and site_speed_test_settings_match is None and ap_uplink_config_match is None and ap_lldp_config_match is None and ap_port_vlans_match is None and ap_bridge_config_match is None and ap_mesh_candidates_match is None and ap_general_config_match is None and ap_ip_setting_match is None and ap_ipv6_setting_match is None and ap_p2p_info_match is None and ap_l3_access_match is None and ap_paring_window_match is None and ap_lag_config_match is None and ap_rf_scan_v2_match is None and ap_management_ssid_match is None and ap_snmp_config_match is None and ap_vlan_v1_match is None and ap_wlan_overrides_match is None:
            self._send(HTTPStatus.NOT_FOUND, {"status": "error", "error": "not_found"})
            return

        configured = _caller_token()
        if configured is None:
            self._send(HTTPStatus.SERVICE_UNAVAILABLE,
                       {"status": "error", "error": "route_disabled"})
            return
        authorization = self.headers.get("Authorization", "")
        scheme, separator, supplied = authorization.partition(" ")
        try:
            supplied_bytes = supplied.encode("ascii") if separator and scheme.lower() == "bearer" and len(supplied) <= 4096 else b""
        except UnicodeEncodeError:
            supplied_bytes = b""
        if not hmac.compare_digest(configured, supplied_bytes):
            self._send(HTTPStatus.UNAUTHORIZED, {"status": "error", "error": "unauthorized"})
            return

        try:
            # The client holds the opaque-reference map between calls. Serialize
            # access so concurrent site refreshes cannot invalidate device lookups.
            with _OPENAPI_LOCK:
                client = _openapi_client()
                if registry_operation == "sites":
                    result = client.list_sites()
                elif registry_operation == "devices":
                    result = client.list_devices(registry_bindings["site_ref"])
                elif registry_operation == "site_switch_health_history":
                    result = client.read_site_switch_health_history(
                        registry_bindings["site_ref"])
                elif registry_operation == "clients":
                    result = client.list_clients(registry_bindings["site_ref"])
                elif registry_operation == "site_client_identity_match":
                    result = client.resolve_site_client_identity(
                        registry_bindings["site_ref"], registry_bindings["client_name"],
                        registry_bindings["ssid_name"])
                elif registry_operation == "client_outage_timeline":
                    if "start_local" in registry_bindings:
                        start_ms, end_ms, zone_name, local_start, local_end = (
                            resolve_local_site_log_window(
                                registry_bindings["start_local"], registry_bindings["end_local"],
                                registry_bindings["time_zone"]))
                        result = client.read_client_outage_timeline(
                            registry_bindings["site_ref"], registry_bindings["client_ref"],
                            start_ms, end_ms)
                        result.update({"time_zone": zone_name,
                                       "window_start_local": local_start.isoformat(),
                                       "window_end_local": local_end.isoformat()})
                    else:
                        result = client.read_client_outage_timeline(
                            registry_bindings["site_ref"], registry_bindings["client_ref"],
                            int(registry_bindings["start_ms"]),
                            int(registry_bindings["end_ms"]))
                elif registry_operation == "site_events_window_summary":
                    if "start_local" in registry_bindings:
                        result = client.read_site_log_local_window_summary(
                            registry_bindings["site_ref"], "events",
                            registry_bindings["start_local"], registry_bindings["end_local"],
                            registry_bindings["time_zone"])
                    else:
                        result = client.read_site_log_window_summary(
                            registry_bindings["site_ref"], "events",
                            int(registry_bindings["start_ms"]), int(registry_bindings["end_ms"]))
                elif registry_operation == "site_alerts_window_summary":
                    if "start_local" in registry_bindings:
                        result = client.read_site_log_local_window_summary(
                            registry_bindings["site_ref"], "alerts",
                            registry_bindings["start_local"], registry_bindings["end_local"],
                            registry_bindings["time_zone"])
                    else:
                        result = client.read_site_log_window_summary(
                            registry_bindings["site_ref"], "alerts",
                            int(registry_bindings["start_ms"]), int(registry_bindings["end_ms"]))
                elif registry_operation == "site_audit_log_window_summary":
                    if "start_local" in registry_bindings:
                        start_ms, end_ms, zone_name, local_start, local_end = (
                            resolve_local_site_log_window(
                                registry_bindings["start_local"], registry_bindings["end_local"],
                                registry_bindings["time_zone"]))
                        result = client.read_site_audit_log_window_summary(
                            registry_bindings["site_ref"], start_ms, end_ms)
                        result.update({"time_zone": zone_name,
                                       "window_start_local": local_start.isoformat(),
                                       "window_end_local": local_end.isoformat()})
                    else:
                        result = client.read_site_audit_log_window_summary(
                            registry_bindings["site_ref"],
                            int(registry_bindings["start_ms"]),
                            int(registry_bindings["end_ms"]))
                elif registry_operation in {"controller_events_window_summary", "controller_alerts_window_summary"}:
                    kind = "events" if registry_operation == "controller_events_window_summary" else "alerts"
                    if "start_local" in registry_bindings:
                        start_ms, end_ms, zone_name, local_start, local_end = (
                            resolve_local_site_log_window(
                                registry_bindings["start_local"], registry_bindings["end_local"],
                                registry_bindings["time_zone"]))
                        result = client.read_controller_log_window_summary(kind, start_ms, end_ms)
                        result.update({"time_zone": zone_name,
                                       "window_start_local": local_start.isoformat(),
                                       "window_end_local": local_end.isoformat()})
                    else:
                        result = client.read_controller_log_window_summary(
                            kind, int(registry_bindings["start_ms"]),
                            int(registry_bindings["end_ms"]))
                elif registry_operation == "controller_audit_log_window_summary":
                    if "start_local" in registry_bindings:
                        start_ms, end_ms, zone_name, local_start, local_end = (
                            resolve_local_site_log_window(
                                registry_bindings["start_local"], registry_bindings["end_local"],
                                registry_bindings["time_zone"]))
                        result = client.read_controller_audit_log_window_summary(start_ms, end_ms)
                        result.update({"time_zone": zone_name,
                                       "window_start_local": local_start.isoformat(),
                                       "window_end_local": local_end.isoformat()})
                    else:
                        result = client.read_controller_audit_log_window_summary(
                            int(registry_bindings["start_ms"]),
                            int(registry_bindings["end_ms"]))
                elif registry_operation == "networks":
                    result = client.list_networks(registry_bindings["site_ref"])
                elif registry_operation == "network_dhcp_server_capabilities":
                    result = client.read_network_dhcp_server_capabilities(
                        registry_bindings["site_ref"], registry_bindings["network_ref"])
                elif registry_operation == "network_dhcp_server_info":
                    result = client.read_network_dhcp_server_info(
                        registry_bindings["site_ref"], registry_bindings["network_ref"])
                elif registry_operation == "site_mac_auth_ssid_inventory":
                    result = client.read_site_mac_auth_ssid_inventory(
                        registry_bindings["site_ref"], int(registry_bindings["type"]))
                elif registry_operation == "ssids":
                    result = client.list_ssids(registry_bindings["site_ref"])
                elif registry_operation == "controller_health":
                    result = client.read_controller_health()
                elif registry_operation == "controller_global_log_notification_summary":
                    result = client.read_controller_global_log_notification_summary()
                elif registry_operation == "controller_upgrade_model_list_summary":
                    result = client.read_controller_upgrade_model_list_summary()
                elif registry_operation == "controller_firmware_inventory_summary":
                    result = client.read_controller_firmware_inventory_summary()
                elif registry_operation == "controller_scenarios":
                    result = client.read_controller_scenarios()
                elif registry_operation == "controller_scenario_differences":
                    result = client.read_controller_scenario_differences()
                elif registry_operation == "controller_threat_severity_summary":
                    result = client.read_controller_threat_severity_summary(
                        int(registry_bindings["start_ms"]),
                        int(registry_bindings["end_ms"]))
                elif registry_operation == "site_threat_window_summary":
                    result = client.read_site_threat_window_summary(
                        registry_bindings["site_ref"],
                        int(registry_bindings["start_ms"]),
                        int(registry_bindings["end_ms"]),
                        registry_bindings["archived"] == "true")
                elif registry_operation == "controller_gateway_wan_status_summary":
                    result = client.read_controller_gateway_wan_status_summary(
                        int(registry_bindings["page_number"]),
                        int(registry_bindings["page_size"]))
                elif registry_operation == "controller_client_recognition":
                    result = client.read_controller_client_recognition()
                elif registry_operation == "controller_device_statistics":
                    result = client.read_controller_device_statistics()
                elif registry_operation == "controller_client_active_timeout":
                    result = client.read_controller_client_active_timeout()
                elif registry_operation == "controller_client_history_retention":
                    result = client.read_controller_client_history_retention()
                elif registry_operation == "controller_audit_notification":
                    result = client.read_controller_audit_notification()
                elif registry_operation == "controller_ui_interface":
                    result = client.read_controller_ui_interface()
                elif registry_operation == "controller_retention":
                    result = client.read_controller_retention()
                elif registry_operation == "controller_dst_info":
                    result = client.read_controller_dst_info()
                elif registry_operation == "controller_experience_improvement":
                    result = client.read_controller_experience_improvement()
                elif registry_operation == "controller_client_detail_info":
                    result = client.read_controller_client_detail_info()
                elif registry_operation == "controller_general_settings":
                    result = client.read_controller_general_settings()
                elif registry_operation == "controller_device_access":
                    result = client.read_controller_device_access()
                elif registry_operation == "controller_backup_schedule":
                    result = client.read_controller_backup_schedule()
                elif registry_operation == "controller_cloud_access":
                    result = client.read_controller_cloud_access()
                elif registry_operation == "controller_device_management":
                    result = client.read_controller_device_management()
                elif registry_operation == "controller_remote_binding":
                    result = client.read_controller_remote_binding()
                elif registry_operation == "controller_backup_result":
                    result = client.read_controller_backup_result()
                elif registry_operation == "controller_backup_inventory_summary":
                    result = client.read_controller_backup_inventory_summary()
                elif registry_operation == "site_backup_inventory_summary":
                    result = client.read_site_backup_inventory_summary(registry_bindings["site_ref"])
                elif registry_operation == "controller_restore_result":
                    result = client.read_controller_restore_result()
                elif registry_operation == "controller_privacy_policy":
                    result = client.read_controller_privacy_policy()
                elif registry_operation == "controller_mail_status":
                    result = client.read_controller_mail_status()
                elif registry_operation == "controller_global_mfa_status":
                    result = client.read_controller_global_mfa_status()
                elif registry_operation == "msp_cloud_access_status":
                    result = client.read_msp_cloud_access_status(registry_bindings["msp_ref"])
                elif registry_operation == "msp_privacy_policy":
                    result = client.read_msp_privacy_policy(registry_bindings["msp_ref"])
                elif registry_operation == "msp_client_detail_info":
                    result = client.read_msp_client_detail_info(registry_bindings["msp_ref"])
                elif registry_operation == "msp_audit_notification":
                    result = client.read_msp_audit_notification(registry_bindings["msp_ref"])
                elif registry_operation == "msp_device_link_topology":
                    result = client.read_msp_device_link_topology(
                        registry_bindings["msp_ref"], registry_bindings["customer_ref"],
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "msp_device_tags":
                    result = client.read_msp_device_tags(registry_bindings["msp_ref"])
                elif registry_operation == "msp_mfa_status":
                    result = client.read_msp_mfa_status(registry_bindings["msp_ref"])
                elif registry_operation == "msp_license_auto_active":
                    result = client.read_msp_license_auto_active(registry_bindings["msp_ref"])
                elif registry_operation == "msp_customer_roles":
                    result = client.read_msp_customer_roles(registry_bindings["msp_ref"])
                elif registry_operation == "msp_dst_info":
                    result = client.read_msp_dst_info(registry_bindings["msp_ref"])
                elif registry_operation == "msp_remote_logging":
                    result = client.read_msp_remote_logging(registry_bindings["msp_ref"])
                elif registry_operation == "msp_mail_server":
                    result = client.read_msp_mail_server(registry_bindings["msp_ref"])
                elif registry_operation == "msp_general_settings":
                    result = client.read_msp_general_settings(registry_bindings["msp_ref"])
                elif registry_operation == "msp_log_notification_settings":
                    result = client.read_msp_log_notification_settings(registry_bindings["msp_ref"])
                elif registry_operation == "msp_data_retention":
                    result = client.read_msp_data_retention(registry_bindings["msp_ref"])
                elif registry_operation == "msp_ui_interface":
                    result = client.read_msp_ui_interface(registry_bindings["msp_ref"])
                elif registry_operation == "msp_user_interface":
                    result = client.read_msp_user_interface(registry_bindings["msp_ref"])
                elif registry_operation == "msp_available_roles":
                    result = client.read_msp_available_roles(registry_bindings["msp_ref"])
                elif registry_operation == "msp_available_customer_roles":
                    result = client.read_msp_available_customer_roles(registry_bindings["msp_ref"])
                elif registry_operation == "msp_dashboard_overall":
                    result = client.read_msp_dashboard_overall(registry_bindings["msp_ref"])
                elif registry_operation == "msp_cluster_nodes":
                    result = client.read_msp_cluster_nodes(registry_bindings["msp_ref"])
                elif registry_operation == "msp_adopt_tip":
                    result = client.read_msp_adopt_tip(registry_bindings["msp_ref"])
                elif registry_operation == "msp_role_summary":
                    result = client.read_msp_role_summary(registry_bindings["msp_ref"])
                elif registry_operation == "site_switch_qos_mode":
                    result = client.read_site_switch_qos_mode(registry_bindings["site_ref"])
                elif registry_operation == "site_switch_qos_scheduler_summary":
                    result = client.read_site_switch_qos_scheduler_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_switch_qos_dscp_summary":
                    result = client.read_site_switch_qos_dscp_summary(registry_bindings["site_ref"])
                elif registry_operation == "controller_remote_logging":
                    result = client.read_controller_remote_logging()
                elif registry_operation == "controller_remote_logging_tip":
                    result = client.read_controller_remote_logging_tip()
                elif registry_operation == "controller_radius_proxy":
                    result = client.read_controller_radius_proxy()
                elif registry_operation == "controller_radius_server":
                    result = client.read_controller_radius_server()
                elif registry_operation == "controller_upgrade_port":
                    result = client.read_controller_upgrade_port()
                elif registry_operation == "controller_portal_port_settings":
                    result = client.read_controller_portal_port_settings()
                elif registry_operation == "controller_port_settings":
                    result = client.read_controller_port_settings()
                elif registry_operation == "controller_status":
                    result = client.read_controller_status()
                elif registry_operation == "controller_logging":
                    result = client.read_controller_logging()
                elif registry_operation == "controller_certificate":
                    result = client.read_controller_certificate()
                elif registry_operation == "controller_roles":
                    result = client.read_controller_roles()
                elif registry_operation == "controller_available_roles":
                    result = client.read_controller_available_roles()
                elif registry_operation == "controller_known_devices":
                    result = client.read_controller_known_devices()
                elif registry_operation == "controller_unknown_devices":
                    result = client.read_controller_unknown_devices()
                elif registry_operation == "controller_device_batch_adopt_summary":
                    result = client.read_controller_device_batch_adopt_summary()
                elif registry_operation == "site_pending_devices_summary":
                    result = client.read_site_pending_devices_summary(registry_bindings["site_ref"])
                elif registry_operation == "device_adopt_result":
                    result = client.read_device_adopt_result(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "device_mac_type":
                    result = client.read_device_mac_type(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "device_link_topology":
                    result = client.read_device_link_topology(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "device_radsec_support":
                    result = client.read_device_radsec_support(registry_bindings["site_ref"])
                elif registry_operation == "device_upgrade_result":
                    result = client.read_device_upgrade_result(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "device_timeline":
                    result = client.read_device_timeline(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "device_inventory_summary":
                    result = client.read_device_inventory_summary(registry_bindings["site_ref"])
                elif registry_operation == "olt_detail_summary":
                    result = client.read_olt_detail_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "olt_ports_summary":
                    result = client.read_olt_ports_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "msp_olt_detail_summary":
                    result = client.read_msp_olt_detail_summary(
                        registry_bindings["msp_ref"], registry_bindings["customer_ref"],
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "msp_olt_eth_config_summary":
                    result = client.read_msp_olt_eth_config_summary(
                        registry_bindings["msp_ref"], registry_bindings["customer_ref"],
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "msp_olt_site_ports_summary":
                    result = client.read_msp_olt_site_ports_summary(
                        registry_bindings["msp_ref"], registry_bindings["customer_ref"],
                        registry_bindings["site_ref"])
                elif registry_operation == "msp_olt_pon_port_config_summary":
                    result = client.read_msp_olt_pon_port_config_summary(
                        registry_bindings["msp_ref"], registry_bindings["customer_ref"],
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "olt_onu_global_status":
                    result = client.read_olt_onu_global_status(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "olt_onu_isolation_status":
                    result = client.read_olt_onu_isolation_status(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "olt_eth_config_summary":
                    result = client.read_olt_eth_config_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "olt_lag_config_summary":
                    result = client.read_olt_lag_config_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "olt_auto_refresh_summary":
                    result = client.read_olt_auto_refresh_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "olt_pon_information_summary":
                    result = client.read_olt_pon_information_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "olt_pon_port_config_page_summary":
                    result = client.read_olt_pon_port_config_page_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"],
                        registry_bindings["page_number"], registry_bindings["page_size"])
                elif registry_operation == "olt_onu_autofind_inventory_summary":
                    result = client.read_olt_onu_autofind_inventory_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"],
                        registry_bindings["pon_port"], registry_bindings["page_number"],
                        registry_bindings["page_size"])
                elif registry_operation == "olt_pon_port_config_summary":
                    result = client.read_olt_pon_port_config_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "olt_service_port_profiles_summary":
                    result = client.read_olt_service_port_profiles_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "olt_onu_auto_auth_status":
                    result = client.read_olt_onu_auto_auth_status(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "olt_onu_autofind_summary":
                    result = client.read_olt_onu_autofind_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "olt_onu_inventory_summary":
                    result = client.read_olt_onu_inventory_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"],
                        registry_bindings["pon_port"])
                elif registry_operation == "olt_onu_reboot_status_summary":
                    result = client.read_olt_onu_reboot_status_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "olt_system_info":
                    result = client.read_olt_system_info(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "olt_system_info_msp":
                    result = client.read_olt_system_info_msp(
                        registry_bindings["msp_ref"], registry_bindings["customer_ref"],
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "msp_ap_health_detail":
                    result = client.read_msp_ap_health_detail(
                        registry_bindings["msp_ref"], registry_bindings["customer_ref"],
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "msp_ap_mesh_statistics":
                    result = client.read_msp_ap_mesh_statistics(
                        registry_bindings["msp_ref"], registry_bindings["customer_ref"],
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "msp_gateway_health_detail":
                    result = client.read_msp_gateway_health_detail(
                        registry_bindings["msp_ref"], registry_bindings["customer_ref"],
                        registry_bindings["site_ref"], registry_bindings["gateway_ref"])
                elif registry_operation == "msp_switch_health_detail":
                    result = client.read_msp_switch_health_detail(
                        registry_bindings["msp_ref"], registry_bindings["customer_ref"],
                        registry_bindings["site_ref"], registry_bindings["switch_ref"])
                elif registry_operation == "msp_ap_health_timeline":
                    result = client.read_msp_ap_health_timeline(
                        registry_bindings["msp_ref"], registry_bindings["customer_ref"],
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "msp_gateway_health_timeline":
                    result = client.read_msp_gateway_health_timeline(
                        registry_bindings["msp_ref"], registry_bindings["customer_ref"],
                        registry_bindings["site_ref"], registry_bindings["gateway_ref"])
                elif registry_operation == "msp_switch_health_timeline":
                    result = client.read_msp_switch_health_timeline(
                        registry_bindings["msp_ref"], registry_bindings["customer_ref"],
                        registry_bindings["site_ref"], registry_bindings["switch_ref"])
                elif registry_operation == "olt_management_interfaces":
                    result = client.read_olt_management_interfaces(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "site_radius_user_summary":
                    result = client.read_site_radius_user_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_entity_summary":
                    result = client.read_site_entity_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_upnp_summary":
                    result = client.read_site_upnp_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_iot_aging_time":
                    result = client.read_site_iot_aging_time(registry_bindings["site_ref"])
                elif registry_operation == "site_iot_radio_summary":
                    result = client.read_site_iot_radio_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_mesh_summary":
                    result = client.read_site_mesh_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_multicast_rate_limit_summary":
                    result = client.read_site_multicast_rate_limit_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_beacon_control_summary":
                    result = client.read_site_beacon_control_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_iot_transmit_power_summary":
                    result = client.read_site_iot_transmit_power_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_remember_setting_summary":
                    result = client.read_site_remember_setting_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_client_connection_summary":
                    result = client.read_site_client_connection_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_poe_usage_summary":
                    result = client.read_site_poe_usage_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_poe_schedule_summary":
                    result = client.read_site_poe_schedule_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_port_schedule_summary":
                    result = client.read_site_port_schedule_summary(
                        registry_bindings["site_ref"],
                        int(registry_bindings["page_number"]),
                        int(registry_bindings["page_size"]))
                elif registry_operation == "site_routing_table_summary":
                    result = client.read_site_routing_table_summary(
                        registry_bindings["site_ref"], registry_bindings["device_type"],
                        int(registry_bindings["page_number"]),
                        int(registry_bindings["page_size"]))
                elif registry_operation == "site_device_counts_summary":
                    result = client.read_site_device_counts_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_ipsec_tunnel_summary":
                    result = client.read_site_ipsec_tunnel_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_client_association_time_summary":
                    result = client.read_site_client_association_time_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_network_activity_summary":
                    result = client.read_site_network_activity_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_client_rssi_distribution_summary":
                    result = client.read_site_client_rssi_distribution_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_ap_rssi_density_summary":
                    result = client.read_site_ap_rssi_density_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_ap_topology_clients_summary":
                    result = client.read_site_ap_topology_clients_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "site_network_delivery_summary":
                    result = client.read_site_network_delivery_summary(
                        registry_bindings["site_ref"], registry_bindings["network_ref"])
                elif registry_operation == "site_lan_port_profiles_summary":
                    result = client.read_site_lan_port_profiles_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_lan_switch_profile_assignments_summary":
                    result = client.read_site_lan_switch_profile_assignments_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_lan_multicast_summary":
                    result = client.read_site_lan_multicast_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_bandwidth_rules_summary":
                    result = client.read_site_bandwidth_rules_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_log_notification_summary":
                    result = client.read_site_log_notification_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_lan_network_interface_summary":
                    result = client.read_site_lan_network_interface_summary(
                        registry_bindings["site_ref"],
                        int(registry_bindings["interface_type"])
                        if "interface_type" in registry_bindings else None)
                elif registry_operation == "site_lan_network_interface_summary":
                    result = client.read_site_lan_network_interface_summary(
                        registry_bindings["site_ref"],
                        int(registry_bindings["interface_type"])
                        if "interface_type" in registry_bindings else None)
                elif registry_operation == "site_client_attachment_distribution_summary":
                    result = client.read_site_client_attachment_distribution_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_client_frequency_distribution_summary":
                    result = client.read_site_client_frequency_distribution_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_device_traffic_summary":
                    result = client.read_site_device_traffic_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_past_client_summary":
                    result = client.read_site_past_client_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_current_client_summary":
                    result = client.read_site_current_client_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_gateway_isp_summary":
                    result = client.read_site_gateway_isp_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_top_ap_retry_drop_summary":
                    result = client.read_site_top_ap_retry_drop_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_active_ap_summary":
                    result = client.read_site_active_ap_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_active_ap_v2_summary":
                    result = client.read_site_active_ap_v2_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_allowed_application_summary":
                    result = client.read_site_allowed_application_summary(
                        registry_bindings["site_ref"], int(registry_bindings["page_number"]),
                        int(registry_bindings["page_size"]))
                elif registry_operation == "site_blocked_application_summary":
                    result = client.read_site_blocked_application_summary(
                        registry_bindings["site_ref"], int(registry_bindings["page_number"]),
                        int(registry_bindings["page_size"]))
                elif registry_operation == "site_dashboard_all_tabs_summary":
                    result = client.read_site_dashboard_all_tabs_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_dashboard_non_overall_tabs_summary":
                    result = client.read_site_dashboard_non_overall_tabs_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_specific_app_traffic_summary":
                    result = client.read_site_specific_app_traffic_summary(
                        registry_bindings["site_ref"], registry_bindings["application_id"])
                elif registry_operation == "site_specific_client_traffic_summary":
                    result = client.read_site_specific_client_traffic_summary(
                        registry_bindings["site_ref"], registry_bindings["client_ref"])
                elif registry_operation == "site_hotspot_statistics_summary":
                    result = client.read_site_hotspot_statistics_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_active_switch_summary":
                    result = client.read_site_active_switch_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_device_memory_summary":
                    result = client.read_site_device_memory_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_switch_dashboard_summary":
                    result = client.read_site_switch_dashboard_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_ap_interference_summary":
                    result = client.read_site_ap_interference_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_application_category_summary":
                    result = client.read_site_application_category_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_category_application_summary":
                    result = client.read_site_category_application_summary(
                        registry_bindings["site_ref"], registry_bindings["family_id"])
                elif registry_operation == "site_category_client_summary":
                    result = client.read_site_category_client_summary(
                        registry_bindings["site_ref"], registry_bindings["family_id"])
                elif registry_operation == "site_active_application_summary":
                    result = client.read_site_active_application_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_active_client_summary":
                    result = client.read_site_active_client_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_cpu_usage_summary":
                    result = client.read_site_cpu_usage_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_client_bubble_summary":
                    result = client.read_site_client_bubble_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_traffic_activity_summary":
                    result = client.read_site_traffic_activity_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_isp_load_summary":
                    result = client.read_site_isp_load_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_vpn_tunnel_summary":
                    result = client.read_site_vpn_tunnel_summary(
                        registry_bindings["site_ref"], int(registry_bindings["vpn_type"]))
                elif registry_operation == "site_open_vpn_tunnel_summary":
                    result = client.read_site_open_vpn_tunnel_summary(
                        registry_bindings["site_ref"], int(registry_bindings["vpn_type"]))
                elif registry_operation == "site_client_activity_summary":
                    result = client.read_site_client_activity_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_client_association_activity_summary":
                    result = client.read_site_client_association_activity_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_client_traffic_summary":
                    result = client.read_site_client_traffic_summary(
                        registry_bindings["site_ref"], int(registry_bindings["page_number"]),
                        int(registry_bindings["page_size"]))
                elif registry_operation == "site_recent_clients_summary":
                    result = client.read_site_recent_clients_summary(
                        registry_bindings["site_ref"], int(registry_bindings["start_ms"]),
                        int(registry_bindings["end_ms"]))
                elif registry_operation == "site_gre_tunnel_summary":
                    result = client.read_site_gre_tunnel_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_ssl_vpn_summary":
                    result = client.read_site_ssl_vpn_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_ssh_summary":
                    result = client.read_site_ssh_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_mld_summary":
                    result = client.read_site_mld_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_templates":
                    result = client.list_site_templates()
                elif registry_operation == "site_template_upnp_summary":
                    result = client.read_site_template_upnp_summary(registry_bindings["site_template_ref"])
                elif registry_operation == "site_template_igmp_summary":
                    result = client.read_site_template_igmp_summary(registry_bindings["site_template_ref"])
                elif registry_operation == "site_template_ssh_summary":
                    result = client.read_site_template_ssh_summary(registry_bindings["site_template_ref"])
                elif registry_operation == "site_template_iptv_summary":
                    result = client.read_site_template_iptv_summary(registry_bindings["site_template_ref"])
                elif registry_operation == "site_template_iptv_settings_summary":
                    result = client.read_site_template_iptv_settings_summary(registry_bindings["site_template_ref"])
                elif registry_operation == "site_igmp_summary":
                    result = client.read_site_igmp_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_iptv_summary":
                    result = client.read_site_iptv_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_device_tag_summary":
                    result = client.read_site_device_tag_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_application_traffic_summary":
                    result = client.read_site_application_traffic_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_wan_lan_status_summary":
                    result = client.read_site_wan_lan_status_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_arp_detect_status_summary":
                    result = client.read_site_arp_detect_status_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_disaster_mode_status":
                    result = client.read_site_disaster_mode_status(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_specification_summary":
                    result = client.read_site_specification_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_portal_logout_domain":
                    result = client.read_site_portal_logout_domain(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_wids_config":
                    result = client.read_site_wids_config(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_wips_config":
                    result = client.read_site_wips_config(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_acl_config_mode":
                    result = client.read_site_acl_config_mode(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_attack_defense_summary":
                    result = client.read_site_attack_defense_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_attack_defense_defaults_summary":
                    result = client.read_site_attack_defense_defaults_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_alg_config":
                    result = client.read_site_alg_config(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_firewall_settings":
                    result = client.read_site_firewall_settings(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_firewall_defaults":
                    result = client.read_site_firewall_defaults(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_bandwidth_control":
                    result = client.read_site_bandwidth_control(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_wan_ports_summary":
                    result = client.read_site_wan_ports_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_wan_unsupported_function_summary":
                    result = client.read_site_wan_unsupported_function_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_wan_port_availability_summary":
                    result = client.read_site_wan_port_availability_summary(
                        registry_bindings["site_ref"], int(registry_bindings["function"]))
                elif registry_operation == "site_virtual_wan_summary":
                    result = client.read_site_virtual_wan_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_wan_max_speed_summary":
                    result = client.read_site_wan_max_speed_summary(
                        registry_bindings["site_ref"], registry_bindings["wan_port_ref"])
                elif registry_operation == "gateway_info_summary":
                    result = client.read_gateway_info_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "site_gateway_sim_sms_support_summary":
                    result = client.read_site_gateway_sim_sms_support_summary(
                        registry_bindings["site_ref"], registry_bindings["gateway_ref"])
                elif registry_operation == "site_ipsec_failover_summary":
                    result = client.read_site_ipsec_failover_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_bridge_device_summary":
                    result = client.read_site_bridge_device_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_upnp_template_comparison":
                    result = client.compare_site_upnp_with_template(
                        registry_bindings["site_ref"], registry_bindings["site_template_ref"])
                elif registry_operation == "site_wan_qos_summary":
                    result = client.read_site_wan_qos_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_gateway_qos_class_summary":
                    result = client.read_site_gateway_qos_class_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_gateway_webfilter_summary":
                    result = client.read_site_gateway_webfilter_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_ap_webfilter_summary":
                    result = client.read_site_ap_webfilter_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_url_filter_general_summary":
                    result = client.read_site_url_filter_general_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_lan_interface_isolation_summary":
                    result = client.read_site_lan_interface_isolation_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_ospf_interface_summary":
                    result = client.read_site_ospf_interface_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_switch_qos_summary":
                    result = client.read_site_switch_qos_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_switch_ddm_summary":
                    result = client.read_site_switch_ddm_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "site_vpn_server_config_summary":
                    result = client.read_site_vpn_server_config_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_vpn_client_config_summary":
                    result = client.read_site_vpn_client_config_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_ids_ips_config_summary":
                    result = client.read_site_ids_ips_config_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_remote_access_tunnel_status_summary":
                    result = client.read_site_remote_access_tunnel_status_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_vpn_server_status_summary":
                    result = client.read_site_vpn_server_status_summary(
                        registry_bindings["site_ref"], int(registry_bindings["vpn_type"]))
                elif registry_operation == "site_vpn_client_status_summary":
                    result = client.read_site_vpn_client_status_summary(
                        registry_bindings["site_ref"], int(registry_bindings["vpn_type"]))
                elif registry_operation == "site_vpn_s2s_status_summary":
                    result = client.read_site_vpn_s2s_status_summary(
                        registry_bindings["site_ref"], int(registry_bindings["vpn_type"]))
                elif registry_operation == "site_s2s_vpn_inventory_summary":
                    result = client.list_site_s2s_vpn_inventory_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_s2s_vpn_v2_summary":
                    result = client.read_site_s2s_vpn_v2_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_s2s_peer_status_summary":
                    result = client.read_site_s2s_peer_status_summary(
                        registry_bindings["site_ref"], registry_bindings["vpn_ref"])
                elif registry_operation == "site_ssid_client_count_summary":
                    result = client.read_site_ssid_client_count_summary(
                        registry_bindings["site_ref"], registry_bindings["ssid_ref"])
                elif registry_operation == "site_ssid_topology_device_summary":
                    result = client.read_site_ssid_topology_device_summary(
                        registry_bindings["site_ref"], registry_bindings["ssid_ref"])
                elif registry_operation == "site_ssid_topology_reference_count":
                    result = client.read_site_ssid_topology_reference_count(
                        registry_bindings["site_ref"], registry_bindings["ssid_ref"])
                elif registry_operation == "site_remote_logging_summary":
                    result = client.read_site_remote_logging_summary(registry_bindings["site_ref"])
                elif registry_operation == "controller_upgrade_log_summary":
                    result = client.read_controller_upgrade_log_summary()
                elif registry_operation == "controller_upgrade_log_inventory":
                    result = client.read_controller_upgrade_log_inventory(
                        int(registry_bindings["page_number"]), int(registry_bindings["page_size"]))
                elif registry_operation == "controller_upgrade_failed_devices_summary":
                    result = client.read_controller_upgrade_failed_devices_summary(
                        registry_bindings["upgrade_log_ref"])
                elif registry_operation == "controller_upgrade_plans_summary":
                    result = client.read_controller_upgrade_plans_summary()
                elif registry_operation == "controller_try_beta_settings_summary":
                    result = client.read_controller_try_beta_settings_summary()
                elif registry_operation == "controller_auto_check_upgrade_summary":
                    result = client.read_controller_auto_check_upgrade_summary()
                elif registry_operation == "site_ipsec_sa_summary":
                    result = client.read_site_ipsec_sa_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_policy_route_summary":
                    result = client.read_site_policy_route_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_static_route_summary":
                    result = client.read_site_static_route_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_nat_exception_summary":
                    result = client.read_site_nat_exception_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_static_route_interface_options_summary":
                    result = client.read_site_static_route_interface_options_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_vlan_network_summary":
                    result = client.read_site_vlan_network_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_lan_network_config_summary":
                    result = client.read_site_lan_network_config_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_lan_network_inventory":
                    result = client.read_site_lan_network_inventory(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_lan_client_inventory_summary":
                    result = client.read_site_lan_client_inventory_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_topology_root_candidates_summary":
                    result = client.read_site_topology_root_candidates_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_topology_snapshot_summary":
                    result = client.read_site_topology_snapshot_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_gateway_qos_service_profiles_summary":
                    result = client.read_site_gateway_qos_service_profiles_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_isolated_preconfig_summary":
                    result = client.read_site_isolated_preconfig_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_vlan_topology_summary":
                    result = client.read_site_vlan_topology_summary(
                        registry_bindings["site_ref"], registry_bindings["network_ref"],
                        int(registry_bindings["vlan_id"]))
                elif registry_operation == "site_vlan_topology_reference_count":
                    result = client.read_site_vlan_topology_reference_count(
                        registry_bindings["site_ref"], registry_bindings["network_ref"],
                        int(registry_bindings["vlan_id"]))
                elif registry_operation == "site_es_network_overview_summary":
                    result = client.read_site_es_network_overview_summary(
                        registry_bindings["site_ref"], registry_bindings["switch_ref"])
                elif registry_operation == "site_agile_switch_general_config_summary":
                    result = client.read_site_agile_switch_general_config_summary(
                        registry_bindings["site_ref"], registry_bindings["switch_ref"])
                elif registry_operation == "site_port_schedule_ports_summary":
                    result = client.read_site_port_schedule_ports_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_internet_summary":
                    result = client.read_site_internet_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_lte_wan_config_summary":
                    result = client.read_site_lte_wan_config_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_internet_load_balance_summary":
                    result = client.read_site_internet_load_balance_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_internet_basic_port_summary":
                    result = client.read_site_internet_basic_port_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_wlan_group_summary":
                    result = client.read_site_wlan_group_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_wlan_group_ssids_summary":
                    result = client.read_site_wlan_group_ssids_summary(
                        registry_bindings["site_ref"], registry_bindings["wlan_group_ref"])
                elif registry_operation == "site_wlan_group_ssid_config_summary":
                    result = client.read_site_wlan_group_ssid_config_summary(
                        registry_bindings["site_ref"], registry_bindings["wlan_group_ref"],
                        registry_bindings["ssid_ref"])
                elif registry_operation == "site_wlan_group_detail_summary":
                    result = client.read_site_wlan_group_detail_summary(
                        registry_bindings["site_ref"], registry_bindings["wlan_group_ref"])
                elif registry_operation == "site_lock_to_ap_brief_inventory":
                    result = client.read_site_lock_to_ap_brief_inventory(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_ineligible_interference_ap_summary":
                    result = client.read_site_ineligible_interference_ap_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_interference_scan_eligible_summary":
                    result = client.read_site_interference_scan_eligible_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_vpn_session_summary":
                    result = client.read_site_vpn_session_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_dhcp_candidate_summary":
                    result = client.read_site_dhcp_candidate_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_network_reservation_summary":
                    result = client.read_site_network_reservation_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_dhcp_reservation_summary":
                    result = client.read_site_dhcp_reservation_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_dhcp_snooping_status":
                    result = client.read_site_dhcp_snooping_status(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_dhcp_snoops_summary":
                    result = client.read_site_dhcp_snoops_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_mdns_rule_summary":
                    result = client.read_site_mdns_rule_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_mdns_profile_summary":
                    result = client.read_site_mdns_profile_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_ddns_summary":
                    result = client.read_site_ddns_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_snmp_settings_summary":
                    result = client.read_site_snmp_settings_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_overview":
                    result = client.read_site_overview(registry_bindings["site_ref"])
                elif site_topology_match is not None:
                    result = client.read_site_topology(site_topology_match.group(1))
                elif registry_operation == "site_longest_client_uptime_summary":
                    result = client.read_site_longest_client_uptime_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_health_timeline":
                    result = client.read_site_health_timeline(registry_bindings["site_ref"])
                elif registry_operation == "site_client_health_timeline":
                    result = client.read_site_client_health_timeline(registry_bindings["site_ref"])
                elif registry_operation == "site_wifi_summary":
                    result = client.read_site_wifi_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_6ghz_ap_presence":
                    result = client.read_site_6ghz_ap_presence(registry_bindings["site_ref"])
                elif registry_operation == "site_setting_existence":
                    result = client.read_site_setting_existence(registry_bindings["site_ref"])
                elif registry_operation == "site_capabilities":
                    result = client.read_site_capabilities(registry_bindings["site_ref"])
                elif registry_operation == "site_reboot_schedule_summary":
                    result = client.read_site_reboot_schedule_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_duplicate_ssid_summary":
                    result = client.read_site_duplicate_ssid_summary(registry_bindings["site_ref"])
                elif registry_operation == "ssid_ap_groups":
                    result = client.read_ssid_ap_groups(
                        registry_bindings["site_ref"], registry_bindings["ssid_ref"])
                elif registry_operation == "site_topology_network_summary":
                    result = client.read_site_topology_network_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_topology_vlan_summary":
                    result = client.read_site_topology_vlan_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_stack_connections_summary":
                    result = client.read_site_stack_connections_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_stack_network_summary":
                    result = client.read_site_stack_network_summary(
                        registry_bindings["site_ref"], registry_bindings["stack_ref"])
                elif registry_operation == "site_stack_static_routing_summary":
                    result = client.read_site_stack_static_routing_summary(
                        registry_bindings["site_ref"], registry_bindings["stack_ref"])
                elif registry_operation == "site_stack_ospf_neighbor_summary":
                    result = client.read_site_stack_ospf_neighbor_summary(
                        registry_bindings["site_ref"], registry_bindings["stack_ref"])
                elif registry_operation == "site_stack_cable_test_log_summary":
                    result = client.read_site_stack_cable_test_log_summary(
                        registry_bindings["site_ref"], registry_bindings["stack_ref"])
                elif registry_operation == "site_intelli_recover_summary":
                    result = client.read_site_intelli_recover_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_port_forwarding_summary":
                    result = client.read_site_port_forwarding_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_stack_dhcp_user_summary":
                    result = client.read_site_stack_dhcp_user_summary(
                        registry_bindings["site_ref"], registry_bindings["stack_ref"])
                elif registry_operation == "site_stack_vlan_interface_summary":
                    result = client.read_site_stack_vlan_interface_summary(
                        registry_bindings["site_ref"], registry_bindings["stack_ref"])
                elif registry_operation == "site_snmp_incompatible_summary":
                    result = client.read_site_snmp_incompatible_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_gateway_general_config_summary":
                    result = client.read_site_gateway_general_config_summary(
                        registry_bindings["site_ref"], registry_bindings["gateway_ref"])
                elif registry_operation == "site_switch_general_config_summary":
                    result = client.read_site_switch_general_config_summary(
                        registry_bindings["site_ref"], registry_bindings["switch_ref"])
                elif registry_operation == "site_switch_oui_vlan_summary":
                    result = client.read_site_switch_oui_vlan_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "controller_sdwan_group_summary":
                    result = client.read_controller_sdwan_group_summary()
                elif registry_operation == "controller_sdwan_group_devices_summary":
                    result = client.read_controller_sdwan_group_devices_summary(
                        registry_bindings["group_ref"])
                elif registry_operation == "site_unresolved_incident_count":
                    result = client.read_site_unresolved_incident_count(registry_bindings["site_ref"])
                elif registry_operation == "site_incident_overview":
                    result = client.read_site_incident_overview(registry_bindings["site_ref"])
                elif registry_operation == "site_incident_distribution":
                    result = client.read_site_incident_distribution(registry_bindings["site_ref"])
                elif registry_operation == "site_incident_category_counts":
                    result = client.read_site_incident_category_counts(registry_bindings["site_ref"])
                elif registry_operation == "site_incident_list":
                    result = client.read_site_incident_list(registry_bindings["site_ref"])
                elif registry_operation == "site_batch_interference_history":
                    result = client.read_site_batch_interference_history(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_batch_interference_ap_summary":
                    result = client.read_site_batch_interference_ap_summary(
                        registry_bindings["site_ref"], registry_bindings["history_ref"])
                elif registry_operation == "site_batch_wifi_interference_summary":
                    result = client.read_site_batch_wifi_interference_summary(
                        registry_bindings["site_ref"], registry_bindings["history_ref"])
                elif registry_operation == "site_batch_channel_load_summary":
                    result = client.read_site_batch_channel_load_summary(
                        registry_bindings["site_ref"], registry_bindings["history_ref"],
                        registry_bindings["device_ref"])
                elif registry_operation == "site_batch_interference_result_summary":
                    result = client.read_site_batch_interference_result_summary(
                        registry_bindings["site_ref"], registry_bindings["history_ref"])
                elif registry_operation == "site_batch_interference_status_summary":
                    result = client.read_site_batch_interference_status_summary(
                        registry_bindings["site_ref"], registry_bindings["history_ref"])
                elif registry_operation == "site_ap_full_channel_detect_status":
                    result = client.read_ap_full_channel_detect_status(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "ap_available_channels_summary":
                    result = client.read_ap_available_channels_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "ap_interference_result_summary":
                    result = client.read_ap_interference_result_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "ap_channel_load_summary":
                    result = client.read_ap_channel_load_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "site_lan_network_detail_summary":
                    result = client.read_site_lan_network_detail_summary(
                        registry_bindings["site_ref"], registry_bindings["network_ref"])
                elif registry_operation == "site_batch_channel_load_summary":
                    result = client.read_site_batch_channel_load_summary(
                        registry_bindings["site_ref"], registry_bindings["history_ref"],
                        registry_bindings["device_ref"])
                elif registry_operation == "device_health_incidents":
                    result = client.read_device_health_incidents(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "ap_overview":
                    result = client.read_ap_overview(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "client_health_incidents":
                    result = client.read_client_health_incidents(
                        registry_bindings["site_ref"], registry_bindings["client_ref"])
                elif registry_operation == "site_incident_detail":
                    result = client.read_site_incident_detail(
                        registry_bindings["site_ref"], registry_bindings["incident_ref"])
                elif registry_operation == "site_incident_notification":
                    result = client.read_site_incident_notification(registry_bindings["site_ref"])
                elif registry_operation == "site_anomaly_event_settings":
                    result = client.read_site_anomaly_event_settings(registry_bindings["site_ref"])
                elif registry_operation == "site_incident_influencing_clients":
                    result = client.read_site_incident_influencing_clients(
                        registry_bindings["site_ref"], registry_bindings["incident_ref"])
                elif registry_operation == "site_incident_influencing_devices":
                    result = client.read_site_incident_influencing_devices(
                        registry_bindings["site_ref"], registry_bindings["incident_ref"])
                elif registry_operation == "site_wlan_group_capacity":
                    result = client.read_site_wlan_group_capacity(registry_bindings["site_ref"])
                elif registry_operation == "site_ap_group_capacity":
                    result = client.read_site_ap_group_capacity(registry_bindings["site_ref"])
                elif registry_operation == "site_ap_group_summary":
                    result = client.read_site_ap_group_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_ap_group_assignment_summary":
                    result = client.read_site_ap_group_assignment_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_ap_group_info_summary":
                    result = client.read_site_ap_group_info_summary(
                        registry_bindings["site_ref"], registry_bindings["group_ref"])
                elif registry_operation == "site_ap_oui_vlan_rules_summary":
                    result = client.read_site_ap_oui_vlan_rules_summary(registry_bindings["site_ref"])
                elif registry_operation == "site_vlan_ssid_usage_summary":
                    result = client.read_site_vlan_ssid_usage_summary(
                        registry_bindings["site_ref"], registry_bindings["network_ref"],
                        int(registry_bindings["vlan_id"]))
                elif registry_operation == "site_vlan_device_usage_summary":
                    result = client.read_site_vlan_device_usage_summary(
                        registry_bindings["site_ref"], registry_bindings["network_ref"],
                        int(registry_bindings["vlan_id"]))
                elif registry_operation == "site_vlan_affected_ports_summary":
                    result = client.read_site_vlan_affected_ports_summary(
                        registry_bindings["site_ref"], registry_bindings["network_ref"],
                        int(registry_bindings["vlan_id"]),
                        int(registry_bindings["page_number"]),
                        int(registry_bindings["page_size"]))
                elif registry_operation == "site_vlan_port_support_summary":
                    result = client.read_site_vlan_port_support_summary(
                        registry_bindings["site_ref"], registry_bindings["network_ref"],
                        int(registry_bindings["vlan_id"]))
                elif registry_operation == "site_wifi_calling_profiles_summary":
                    result = client.read_site_wifi_calling_profiles_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_client_filter_options_summary":
                    result = client.read_site_client_filter_options_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_eap_dot1x_candidates_summary":
                    result = client.read_site_eap_dot1x_candidates_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_switch_dot1x_candidates_summary":
                    result = client.read_site_switch_dot1x_candidates_summary(
                        registry_bindings["site_ref"])
                elif registry_operation == "site_switch_support":
                    result = client.read_site_switch_support(registry_bindings["site_ref"])
                elif switch_port_tags_match is not None:
                    result = client.list_switch_port_tags(registry_bindings["site_ref"])
                elif registry_operation == "ap_wifi_interference":
                    result = client.read_ap_wifi_neighbors(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "ap_speed_test_results":
                    result = client.read_ap_speed_test_results(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "ap_ssid_override_audit_summary":
                    result = client.read_ap_ssid_override_audit_summary(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif registry_operation == "experience_index":
                    result = client.read_experience_index(registry_bindings["site_ref"])
                elif registry_operation == "rf_planning_result":
                    result = client.read_rf_planning_result(registry_bindings["site_ref"])
                elif registry_operation == "rf_planning_dashboard":
                    result = client.read_rf_planning_dashboard(registry_bindings["site_ref"])
                elif registry_operation == "rf_planning_dashboard_history":
                    result = client.read_rf_planning_dashboard_history(registry_bindings["site_ref"])
                elif registry_operation == "rf_planning_dashboard_current":
                    result = client.read_rf_planning_dashboard_current(registry_bindings["site_ref"])
                elif registry_operation == "rf_planning_detail":
                    result = client.read_rf_planning_detail(registry_bindings["site_ref"])
                elif registry_operation == "rf_planning_history":
                    result = client.read_rf_planning_history(registry_bindings["site_ref"])
                elif registry_operation == "rf_planning_history_detail":
                    result = client.read_rf_planning_history_detail(
                        registry_bindings["site_ref"], registry_bindings["history_ref"])
                elif registry_operation == "rf_planning_recent_history":
                    result = client.read_rf_planning_recent_history(registry_bindings["site_ref"])
                elif registry_operation == "rf_excluded_aps":
                    result = client.read_rf_excluded_aps(registry_bindings["site_ref"])
                elif registry_operation == "rf_deploy_history":
                    result = client.read_rf_deploy_history(registry_bindings["site_ref"])
                elif wifi_health_match is not None:
                    result = client.read_wifi_health(wifi_health_match.group(1))
                elif wifi_health_details_match is not None:
                    result = client.read_wifi_subhealth(wifi_health_details_match.group(1))
                elif band_steering_match is not None:
                    result = client.read_band_steering(band_steering_match.group(1))
                elif rrm_settings_match is not None:
                    result = client.read_rrm_settings(rrm_settings_match.group(1))
                elif roaming_settings_match is not None:
                    result = client.read_roaming_settings(roaming_settings_match.group(1))
                elif rrm_incompatible_match is not None:
                    result = client.read_rrm_incompatible(rrm_incompatible_match.group(1))
                elif site_dashboard_channels_match is not None:
                    result = client.read_site_dashboard_channels(site_dashboard_channels_match.group(1))
                elif site_client_signal_distribution_match is not None:
                    result = client.read_site_client_signal_distribution(
                        site_client_signal_distribution_match.group(1))
                elif site_led_match is not None:
                    result = client.read_site_led(site_led_match.group(1))
                elif site_lldp_match is not None:
                    result = client.read_site_lldp(site_lldp_match.group(1))
                elif site_dpi_match is not None:
                    result = client.read_site_dpi_logging(site_dpi_match.group(1))
                elif gateway_voip_match is not None:
                    result = client.read_gateway_voip(gateway_voip_match.group(1))
                elif gateway_tag_qos_match is not None:
                    result = client.read_gateway_tag_qos(gateway_tag_qos_match.group(1))
                elif site_channel_limit_match is not None:
                    result = client.read_site_channel_limit(site_channel_limit_match.group(1))
                elif ap_channel_limit_match is not None:
                    result = client.read_ap_channel_limit(
                        ap_channel_limit_match.group(1), ap_channel_limit_match.group(2))
                elif ap_ofdma_match is not None:
                    result = client.read_ap_ofdma(
                        ap_ofdma_match.group(1), ap_ofdma_match.group(2))
                elif ap_qos_match is not None:
                    result = client.read_ap_qos(
                        ap_qos_match.group(1), ap_qos_match.group(2))
                elif ap_lag_match is not None:
                    result = client.read_ap_lag(
                        ap_lag_match.group(1), ap_lag_match.group(2))
                elif ap_load_balance_match is not None:
                    result = client.read_ap_load_balance(
                        ap_load_balance_match.group(1), ap_load_balance_match.group(2))
                elif ap_antenna_match is not None:
                    result = client.read_ap_antenna(
                        ap_antenna_match.group(1), ap_antenna_match.group(2))
                elif ap_antenna_gain_match is not None:
                    result = client.read_ap_antenna_gain(
                        ap_antenna_gain_match.group(1), ap_antenna_gain_match.group(2))
                elif ap_power_saving_match is not None:
                    result = client.read_ap_power_saving(
                        ap_power_saving_match.group(1), ap_power_saving_match.group(2))
                elif ap_wired_uplink_match is not None:
                    result = client.read_ap_wired_uplink(
                        ap_wired_uplink_match.group(1), ap_wired_uplink_match.group(2))
                elif ap_uplink_config_match is not None:
                    result = client.read_ap_uplink_config(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_lldp_config_match is not None:
                    result = client.read_ap_lldp_config(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_port_vlans_match is not None:
                    result = client.read_ap_port_vlans(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_bridge_config_match is not None:
                    result = client.read_ap_bridge_config(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_mesh_candidates_match is not None:
                    result = client.read_ap_mesh_candidates(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_general_config_match is not None:
                    result = client.read_ap_general_config(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_ip_setting_match is not None:
                    result = client.read_ap_ip_setting(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_ipv6_setting_match is not None:
                    result = client.read_ap_ipv6_setting(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_p2p_info_match is not None:
                    result = client.read_ap_p2p_info(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_l3_access_match is not None:
                    result = client.read_ap_l3_access(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_paring_window_match is not None:
                    result = client.read_ap_paring_window(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_lag_config_match is not None:
                    result = client.read_ap_lag_config(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_rf_scan_v2_match is not None:
                    result = client.read_ap_rf_scan_v2(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_management_ssid_match is not None:
                    result = client.read_ap_management_ssid(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_snmp_config_match is not None:
                    result = client.read_ap_snmp_config(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_vlan_v1_match is not None:
                    result = client.read_ap_vlan_v1(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_wlan_overrides_match is not None:
                    result = client.read_ap_wlan_overrides(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_wired_downlink_match is not None:
                    result = client.read_ap_wired_downlink(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_ports_match is not None:
                    result = client.list_ap_ports(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif ap_lan_traffic_match is not None:
                    result = client.read_ap_lan_traffic(
                        ap_lan_traffic_match.group(1), ap_lan_traffic_match.group(2))
                elif ap_vlan_match is not None:
                    result = client.read_ap_vlan(ap_vlan_match.group(1), ap_vlan_match.group(2))
                elif device_firmware_match is not None:
                    result = client.read_device_firmware(device_firmware_match.group(1), device_firmware_match.group(2))
                elif ap_health_match is not None:
                    result = client.read_ap_health(ap_health_match.group(1), ap_health_match.group(2))
                elif ap_health_timeline_match is not None:
                    result = client.read_ap_health_timeline(
                        ap_health_timeline_match.group(1), ap_health_timeline_match.group(2))
                elif ap_afc_match is not None:
                    result = client.read_ap_afc(ap_afc_match.group(1), ap_afc_match.group(2))
                elif ap_afc_status_match is not None:
                    result = client.read_ap_afc_status(ap_afc_status_match.group(1), ap_afc_status_match.group(2))
                elif ap_retry_drop_match is not None:
                    result = client.read_ap_retry_drop(ap_retry_drop_match.group(1))
                elif ap_mesh_match is not None:
                    result = client.read_ap_mesh_statistics(ap_mesh_match.group(1), ap_mesh_match.group(2))
                elif client_detail_match is not None:
                    result = client.read_client_detail(client_detail_match.group(1), client_detail_match.group(2))
                elif client_connections_match is not None:
                    result = client.read_client_connection_history(client_connections_match.group(1), client_connections_match.group(2))
                elif client_history_match is not None:
                    result = client.read_client_history(client_history_match.group(1), client_history_match.group(2))
                elif client_timeline_match is not None:
                    result = client.read_client_timeline(
                        client_timeline_match.group(1), client_timeline_match.group(2),
                        client_timeline_match.group(3))
                elif client_health_detail_v2_match is not None:
                    result = client.read_client_health_detail_v2(
                        client_health_detail_v2_match.group(1), client_health_detail_v2_match.group(2))
                elif client_health_detail_v2_match is not None:
                    result = client.read_client_health_detail_v2(
                        client_health_detail_v2_match.group(1), client_health_detail_v2_match.group(2))
                elif client_health_match is not None:
                    result = client.read_client_health(client_health_match.group(1), client_health_match.group(2))
                elif client_health_timeline_match is not None:
                    result = client.read_client_health_timeline(
                        client_health_timeline_match.group(1), client_health_timeline_match.group(2))
                elif wlan_groups_match is not None:
                    result = client.list_wlan_groups(wlan_groups_match.group(1))
                elif ssid_config_match is not None:
                    result = client.read_ssid_configuration(ssid_config_match.group(1), ssid_config_match.group(2))
                elif ap_available_channels_match is not None:
                    result = client.read_ap_available_channels(ap_available_channels_match.group(1), ap_available_channels_match.group(2))
                elif ap_rf_scan_match is not None:
                    result = client.read_ap_rf_scan(ap_rf_scan_match.group(1), ap_rf_scan_match.group(2))
                elif ap_wifi_neighbors_match is not None:
                    result = client.read_ap_wifi_neighbors(ap_wifi_neighbors_match.group(1), ap_wifi_neighbors_match.group(2))
                elif gateway_wan_match is not None:
                    result = client.read_gateway_wan_status(gateway_wan_match.group(1), gateway_wan_match.group(2))
                elif gateway_wan_health_match is not None:
                    result = client.read_gateway_wan_health(gateway_wan_health_match.group(1), gateway_wan_health_match.group(2))
                elif gateway_health_match is not None:
                    result = client.read_gateway_health(
                        gateway_health_match.group(1), gateway_health_match.group(2))
                elif gateway_health_timeline_match is not None:
                    result = client.read_gateway_health_timeline(
                        gateway_health_timeline_match.group(1), gateway_health_timeline_match.group(2))
                elif gateway_lan_status_match is not None:
                    result = client.read_gateway_lan_status(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif gateway_ports_match is not None:
                    result = client.read_gateway_ports(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif gateway_speed_test_results_match is not None:
                    result = client.read_gateway_speed_test_results(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif site_speed_test_settings_match is not None:
                    result = client.read_site_speed_test_settings(registry_bindings["site_ref"])
                elif gateway_dhcp_leases_match is not None:
                    result = client.list_gateway_dhcp_leases(
                        registry_bindings["site_ref"], registry_bindings["gateway_ref"])
                elif gateway_internet_info_match is not None:
                    result = client.read_gateway_internet_info(
                        registry_bindings["site_ref"], registry_bindings["device_ref"])
                elif gateway_ipv6_match is not None:
                    result = client.read_gateway_ipv6_ip_passthrough(
                        gateway_ipv6_match.group(1), gateway_ipv6_match.group(2))
                elif switch_poe_match is not None:
                    result = client.read_switch_port_poe_state(
                        switch_poe_match.group(1), switch_poe_match.group(2),
                        int(switch_poe_match.group(3)))
                elif switch_port_status_match is not None:
                    result = client.read_switch_port_status(
                        switch_port_status_match.group(1), switch_port_status_match.group(2),
                        int(switch_port_status_match.group(3)))
                elif switch_ports_match is not None:
                    result = client.read_switch_ports(switch_ports_match.group(1), switch_ports_match.group(2))
                elif switch_port_counters_match is not None:
                    result = client.read_switch_port_counters(
                        switch_port_counters_match.group(1), switch_port_counters_match.group(2))
                elif switch_port_poe_info_match is not None:
                    result = client.read_switch_port_poe_info(
                        switch_port_poe_info_match.group(1), switch_port_poe_info_match.group(2))
                elif switch_vlans_match is not None:
                    result = client.read_switch_vlans(switch_vlans_match.group(1), switch_vlans_match.group(2))
                elif switch_lldp_match is not None:
                    result = client.read_switch_lldp_neighbors(switch_lldp_match.group(1), switch_lldp_match.group(2))
                elif switch_health_match is not None:
                    result = client.read_switch_health(switch_health_match.group(1), switch_health_match.group(2))
                elif switch_health_timeline_match is not None:
                    result = client.read_switch_health_timeline(switch_health_timeline_match.group(1), switch_health_timeline_match.group(2))
                elif switch_sdm_usage_match is not None:
                    result = client.read_switch_sdm_usage(switch_sdm_usage_match.group(1), switch_sdm_usage_match.group(2))
                elif switch_cable_test_logs_match is not None:
                    result = client.read_switch_cable_test_logs(switch_cable_test_logs_match.group(1), switch_cable_test_logs_match.group(2))
                elif switch_cable_test_full_results_match is not None:
                    result = client.read_switch_cable_test_full_results(switch_cable_test_full_results_match.group(1), switch_cable_test_full_results_match.group(2))
                elif switch_cable_test_increment_results_match is not None:
                    result = client.read_switch_cable_test_increment_results(switch_cable_test_increment_results_match.group(1), switch_cable_test_increment_results_match.group(2))
                elif switch_cable_test_ports_match is not None:
                    result = client.read_switch_cable_test_ports(switch_cable_test_ports_match.group(1), switch_cable_test_ports_match.group(2))
                elif switch_dhcp_users_match is not None:
                    result = client.list_switch_dhcp_users(switch_dhcp_users_match.group(1), switch_dhcp_users_match.group(2))
                elif switch_ospf_neighbors_match is not None:
                    result = client.list_switch_ospf_neighbors(switch_ospf_neighbors_match.group(1), switch_ospf_neighbors_match.group(2))
                elif switch_port_networks_match is not None:
                    result = client.list_switch_port_networks(switch_port_networks_match.group(1), switch_port_networks_match.group(2))
                elif switch_exist_networks_match is not None:
                    result = client.list_switch_exist_networks(switch_exist_networks_match.group(1), switch_exist_networks_match.group(2))
                elif switch_networks_match is not None:
                    result = client.list_switch_networks(switch_networks_match.group(1), switch_networks_match.group(2))
                elif switch_interfaces_match is not None:
                    result = client.list_switch_interfaces(switch_interfaces_match.group(1), switch_interfaces_match.group(2))
                elif switch_routing_table_match is not None:
                    result = client.list_switch_routing_table(switch_routing_table_match.group(1), switch_routing_table_match.group(2))
                elif switch_static_routes_match is not None:
                    result = client.list_switch_static_routes(switch_static_routes_match.group(1), switch_static_routes_match.group(2))
                elif switch_vrfs_match is not None:
                    result = client.list_switch_vrfs(switch_vrfs_match.group(1), switch_vrfs_match.group(2))
                elif switch_vlan_interfaces_match is not None:
                    result = client.list_switch_vlan_interfaces(switch_vlan_interfaces_match.group(1), switch_vlan_interfaces_match.group(2))
                elif switch_statistics_match is not None:
                    result = client.read_switch_statistics(switch_statistics_match.group(1), switch_statistics_match.group(2))
                elif firewall_rules_match is not None:
                    result = client.list_gateway_firewall_rules(firewall_rules_match.group(1))
                elif switch_acl_match is not None:
                    result = client.list_switch_firewall_rules(switch_acl_match.group(1))
                elif ap_acl_match is not None:
                    result = client.list_ap_firewall_rules(ap_acl_match.group(1))
                elif dhcp_leases_match is not None:
                    result = client.list_dhcp_leases(dhcp_leases_match.group(1))
                elif dns_cache_match is not None:
                    result = client.read_dns_cache_settings(dns_cache_match.group(1))
                elif dns_proxy_match is not None:
                    result = client.read_dns_proxy_settings(dns_proxy_match.group(1))
                elif dns_records_match is not None:
                    result = client.list_lan_dns_records(dns_records_match.group(1))
                elif events_match is not None:
                    result = client.list_site_events(events_match.group(1))
                elif alerts_match is not None:
                    result = client.list_site_alerts(alerts_match.group(1))
                elif site_rogue_ap_results_match is not None:
                    result = client.read_site_rogue_ap_results(
                        registry_bindings["site_ref"])
                elif site_wids_summary_match is not None:
                    result = client.read_site_wids_summary(
                        registry_bindings["site_ref"])
                elif site_wids_blacklist_summary_match is not None:
                    result = client.read_site_wids_blacklist_summary(
                        registry_bindings["site_ref"])
                else:
                    assert ap_match is not None
                    result = client.read_ap_radio_part(
                        ap_match.group(1), ap_match.group(2), _AP_PARTS[ap_match.group(3)])
        except OpenApiError as exc:
            config_errors = {
                "openapi_configuration_missing", "openapi_configuration_invalid",
                "controller_url_invalid", "controller_id_invalid", "tls_trust_mode_invalid",
                "controller_certificate_pin_invalid", "controller_certificate_pin_required",
                "pagination_limit_invalid", "response_limit_invalid", "timeout_invalid",
                "credential_file_unavailable", "credential_file_invalid",
                "reference_key_unconfigured", "reference_key_configuration_invalid",
                "reference_key_path_invalid", "reference_key_platform_unsupported",
                "reference_key_file_unavailable", "reference_key_file_invalid",
                "reference_key_permissions_invalid", "reference_key_read_failed",
            }
            status = HTTPStatus.SERVICE_UNAVAILABLE if exc.code in config_errors else HTTPStatus.BAD_GATEWAY
            error_body: dict[str, object] = {"status": "error", "error": exc.code}
            if type(exc.upstream_http_status) is int:
                error_body["upstream_http_status"] = exc.upstream_http_status
            if type(exc.upstream_error_code) is int:
                error_body["upstream_error_code"] = exc.upstream_error_code
            self._send(status, error_body)
            return
        self._send(HTTPStatus.OK, result)

    def log_message(self, fmt: str, *args: object) -> None:
        # Log only fixed labels; method, target, and format arguments are caller-controlled.
        method = "GET" if self.command == "GET" else "OTHER"
        route = self.path.partition("?")[0]
        if route not in {"/healthz", "/state", "/omada/controller-info", "/v1/sites"}:
            if route == "/v1/controller/health":
                route = "/v1/controller/health"
            elif re.fullmatch(r"/v1/change-plans/(radio|dns-cache|ssid|gateway-ipv6|poe|switch-port-status|switch-port-name|band-steering|rrm-mode|site-led|ap-afc|site-lldp|ap-channel-limit|ap-ofdma|ap-qos|site-dpi|gateway-voip|gateway-tag-qos|switch-cable-test|switch-cable-test-cancel|controller-radius-proxy)/in-doubt", route):
                route = "/v1/change-plans/<kind>/in-doubt"
            elif re.fullmatch(r"/v1/change-plans/(radio|dns-cache|ssid|gateway-ipv6|poe|switch-port-status|switch-port-name|band-steering|rrm-mode|site-led|ap-afc|site-lldp|ap-channel-limit|ap-ofdma|ap-qos|site-dpi|gateway-voip|gateway-tag-qos|switch-cable-test|switch-cable-test-cancel|controller-radius-proxy)/[0-9a-f]{48}", route):
                route = "/v1/change-plans/<kind>/<plan>"
            elif re.fullmatch(r"/v1/change-plans/(radio|dns-cache|ssid|gateway-ipv6|poe|switch-port-status|switch-port-name|band-steering|rrm-mode|site-led|ap-afc|site-lldp|ap-channel-limit|ap-ofdma|ap-qos|site-dpi|gateway-voip|gateway-tag-qos|switch-cable-test|switch-cable-test-cancel|controller-radius-proxy)/[0-9a-f]{48}/close", route):
                route = "/v1/change-plans/<kind>/<plan>/close"
            elif re.fullmatch(r"/v1/controller/settings/radius-proxy-preview", route):
                route = "/v1/controller/settings/radius-proxy-preview"
            elif re.fullmatch(r"/v1/controller-radius-proxy-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/controller-radius-proxy-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/switches/[0-9a-f]{24}/ports/[0-9]{1,5}/name-preview", route):
                route = "/v1/sites/<ref>/switches/<ref>/ports/<port>/name-preview"
            elif re.fullmatch(r"/v1/switch-port-name-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/switch-port-name-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/switches/[0-9a-f]{24}/cable-test-preview", route):
                route = "/v1/sites/<ref>/switches/<ref>/cable-test-preview"
            elif re.fullmatch(r"/v1/switch-cable-test-plans/[0-9a-f]{48}/(?:apply|status|cancel-preview)", route):
                route = "/v1/switch-cable-test-plans/<plan>/<action>"
            elif re.fullmatch(r"/v1/switch-cable-test-cancel-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/switch-cable-test-cancel-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/application-control-preview", route):
                route = "/v1/sites/<ref>/application-control-preview"
            elif re.fullmatch(r"/v1/site-dpi-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/site-dpi-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/qos/gateway/voip-prioritization-preview", route):
                route = "/v1/sites/<ref>/qos/gateway/voip-prioritization-preview"
            elif re.fullmatch(r"/v1/gateway-voip-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/gateway-voip-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/qos/gateway/tag-outbound-traffic", route):
                route = "/v1/sites/<ref>/qos/gateway/tag-outbound-traffic"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/qos/gateway/tag-outbound-traffic-preview", route):
                route = "/v1/sites/<ref>/qos/gateway/tag-outbound-traffic-preview"
            elif re.fullmatch(r"/v1/gateway-tag-qos-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/gateway-tag-qos-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/health/summary", route):
                route = "/v1/sites/<ref>/health/summary"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/topology", route):
                route = "/v1/sites/<ref>/topology"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/health/timeline", route):
                route = "/v1/sites/<ref>/health/timeline"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/wifi/health/timeline", route):
                route = "/v1/sites/<ref>/wifi/health/timeline"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/wifi/health/details", route):
                route = "/v1/sites/<ref>/wifi/health/details"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/wifi/band-steering", route):
                route = "/v1/sites/<ref>/wifi/band-steering"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/wifi/optimization", route):
                route = "/v1/sites/<ref>/wifi/optimization"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/wifi/roaming", route):
                route = "/v1/sites/<ref>/wifi/roaming"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/wifi/rrm-incompatible", route):
                route = "/v1/sites/<ref>/wifi/rrm-incompatible"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/wifi/channels", route):
                route = "/v1/sites/<ref>/wifi/channels"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/wifi/client-signal-distribution", route):
                route = "/v1/sites/<ref>/wifi/client-signal-distribution"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/led", route):
                route = "/v1/sites/<ref>/led"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/lldp", route):
                route = "/v1/sites/<ref>/lldp"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/lldp-preview", route):
                route = "/v1/sites/<ref>/lldp-preview"
            elif re.fullmatch(r"/v1/site-lldp-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/site-lldp-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/wifi/channel-limit", route):
                route = "/v1/sites/<ref>/wifi/channel-limit"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/channel-limit", route):
                route = "/v1/sites/<ref>/aps/<ref>/channel-limit"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/channel-limit-preview", route):
                route = "/v1/sites/<ref>/aps/<ref>/channel-limit-preview"
            elif re.fullmatch(r"/v1/ap-channel-limit-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/ap-channel-limit-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/ofdma", route):
                route = "/v1/sites/<ref>/aps/<ref>/ofdma"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/qos", route):
                route = "/v1/sites/<ref>/aps/<ref>/qos"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/lag", route):
                route = "/v1/sites/<ref>/aps/<ref>/lag"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/load-balance", route):
                route = "/v1/sites/<ref>/aps/<ref>/load-balance"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/antenna", route):
                route = "/v1/sites/<ref>/aps/<ref>/antenna"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/antenna-gain", route):
                route = "/v1/sites/<ref>/aps/<ref>/antenna-gain"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/power-saving", route):
                route = "/v1/sites/<ref>/aps/<ref>/power-saving"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/wired-uplink", route):
                route = "/v1/sites/<ref>/aps/<ref>/wired-uplink"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/lan-traffic", route):
                route = "/v1/sites/<ref>/aps/<ref>/lan-traffic"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/vlan", route):
                route = "/v1/sites/<ref>/aps/<ref>/vlan"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/ofdma-preview", route):
                route = "/v1/sites/<ref>/aps/<ref>/ofdma-preview"
            elif re.fullmatch(r"/v1/ap-ofdma-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/ap-ofdma-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/ap-qos-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/ap-qos-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/led-preview", route):
                route = "/v1/sites/<ref>/led-preview"
            elif re.fullmatch(r"/v1/site-led-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/site-led-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/wifi/band-steering-preview", route):
                route = "/v1/sites/<ref>/wifi/band-steering-preview"
            elif re.fullmatch(r"/v1/band-steering-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/band-steering-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/wifi/optimization-preview", route):
                route = "/v1/sites/<ref>/wifi/optimization-preview"
            elif re.fullmatch(r"/v1/rrm-mode-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/rrm-mode-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/devices", route):
                route = "/v1/sites/<ref>/devices"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/devices/[0-9a-f]{24}/firmware", route):
                route = "/v1/sites/<ref>/devices/<ref>/firmware"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/health", route):
                route = "/v1/sites/<ref>/aps/<ref>/health"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/health/timeline", route):
                route = "/v1/sites/<ref>/aps/<ref>/health/timeline"
            elif re.fullmatch(
                r"/v1/sites/[0-9a-f]{24}/clients/[0-9a-f]{24}/timeline/(connect|association|roaming|disconnect)",
                route):
                route = "/v1/sites/<ref>/clients/<ref>/timeline/<kind>"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/afc", route):
                route = "/v1/sites/<ref>/aps/<ref>/afc"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/afc/status", route):
                route = "/v1/sites/<ref>/aps/<ref>/afc/status"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/afc-preview", route):
                route = "/v1/sites/<ref>/aps/<ref>/afc-preview"
            elif re.fullmatch(r"/v1/ap-afc-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/ap-afc-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/retry-drop", route):
                route = "/v1/sites/<ref>/aps/retry-drop"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/mesh", route):
                route = "/v1/sites/<ref>/aps/<ref>/mesh"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/clients", route):
                route = "/v1/sites/<ref>/clients"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/clients/[0-9a-f]{24}", route):
                route = "/v1/sites/<ref>/clients/<ref>"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/clients/[0-9a-f]{24}/connections", route):
                route = "/v1/sites/<ref>/clients/<ref>/connections"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/clients/[0-9a-f]{24}/history", route):
                route = "/v1/sites/<ref>/clients/<ref>/history"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/clients/[0-9a-f]{24}/health", route):
                route = "/v1/sites/<ref>/clients/<ref>/health"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/clients/[0-9a-f]{24}/health/timeline", route):
                route = "/v1/sites/<ref>/clients/<ref>/health/timeline"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/networks", route):
                route = "/v1/sites/<ref>/networks"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/ssids", route):
                route = "/v1/sites/<ref>/ssids"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/rf-scan", route):
                route = "/v1/sites/<ref>/aps/<ref>/rf-scan"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/wifi-neighbors", route):
                route = "/v1/sites/<ref>/aps/<ref>/wifi-neighbors"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/gateways/[0-9a-f]{24}/wan-status", route):
                route = "/v1/sites/<ref>/gateways/<ref>/wan-status"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/gateways/[0-9a-f]{24}/wan-health", route):
                route = "/v1/sites/<ref>/gateways/<ref>/wan-health"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/gateways/[0-9a-f]{24}/health", route):
                route = "/v1/sites/<ref>/gateways/<ref>/health"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/gateways/[0-9a-f]{24}/health/timeline", route):
                route = "/v1/sites/<ref>/gateways/<ref>/health/timeline"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/gateways/[0-9a-f]{24}/ipv6-ip-passthrough", route):
                route = "/v1/sites/<ref>/gateways/<ref>/ipv6-ip-passthrough"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/gateways/[0-9a-f]{24}/ipv6-ip-passthrough-preview", route):
                route = "/v1/sites/<ref>/gateways/<ref>/ipv6-ip-passthrough-preview"
            elif re.fullmatch(r"/v1/gateway-ipv6-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/gateway-ipv6-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/switches/[0-9a-f]{24}/ports/[0-9]{1,5}/poe", route):
                route = "/v1/sites/<ref>/switches/<ref>/ports/<port>/poe"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/switches/[0-9a-f]{24}/ports/[0-9]{1,5}/poe-preview", route):
                route = "/v1/sites/<ref>/switches/<ref>/ports/<port>/poe-preview"
            elif re.fullmatch(r"/v1/poe-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/poe-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/switches/[0-9a-f]{24}/ports/[0-9]{1,5}/status", route):
                route = "/v1/sites/<ref>/switches/<ref>/ports/<port>/status"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/switches/[0-9a-f]{24}/ports/[0-9]{1,5}/status-preview", route):
                route = "/v1/sites/<ref>/switches/<ref>/ports/<port>/status-preview"
            elif re.fullmatch(r"/v1/switch-port-status-plans/[0-9a-f]{48}/apply", route):
                route = "/v1/switch-port-status-plans/<plan>/apply"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/switches/[0-9a-f]{24}/ports", route):
                route = "/v1/sites/<ref>/switches/<ref>/ports"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/switches/[0-9a-f]{24}/ports/counters", route):
                route = "/v1/sites/<ref>/switches/<ref>/ports/counters"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/switches/[0-9a-f]{24}/ports/poe-info", route):
                route = "/v1/sites/<ref>/switches/<ref>/ports/poe-info"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/switches/[0-9a-f]{24}/vlans", route):
                route = "/v1/sites/<ref>/switches/<ref>/vlans"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/switches/[0-9a-f]{24}/lldp-neighbors", route):
                route = "/v1/sites/<ref>/switches/<ref>/lldp-neighbors"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/switches/[0-9a-f]{24}/health", route):
                route = "/v1/sites/<ref>/switches/<ref>/health"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/firewall/gateway-acls", route):
                route = "/v1/sites/<ref>/firewall/gateway-acls"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/firewall/switch-acls", route):
                route = "/v1/sites/<ref>/firewall/switch-acls"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/firewall/ap-acls", route):
                route = "/v1/sites/<ref>/firewall/ap-acls"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/dhcp/leases", route):
                route = "/v1/sites/<ref>/dhcp/leases"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/dns/cache", route):
                route = "/v1/sites/<ref>/dns/cache"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/dns/proxy", route):
                route = "/v1/sites/<ref>/dns/proxy"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/dns/records", route):
                route = "/v1/sites/<ref>/dns/records"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/events", route):
                route = "/v1/sites/<ref>/events"
            elif re.fullmatch(r"/v1/sites/[0-9a-f]{24}/alerts", route):
                route = "/v1/sites/<ref>/alerts"
            elif re.fullmatch(
                r"/v1/sites/[0-9a-f]{24}/aps/[0-9a-f]{24}/(radio-config|radios|scan-status|channel-load)",
                route,
            ):
                route = "/v1/sites/<ref>/aps/<ref>/<part>"
            else:
                route = "<other>"
        print("http", method, route)


def main() -> None:
    host = os.getenv("LISTEN_HOST", "0.0.0.0")
    port = int(os.getenv("LISTEN_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"omada-universal-connector listening on {host}:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        with _OPENAPI_LOCK:
            if _JOURNAL_RUNTIME is not None:
                _JOURNAL_RUNTIME.close()


if __name__ == "__main__":
    main()
