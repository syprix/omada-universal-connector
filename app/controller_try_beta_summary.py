"""Redacted summary of the controller's firmware preview setting."""
from __future__ import annotations

from collections.abc import Mapping


class ControllerTryBetaError(ValueError):
    pass


def summarize_try_beta_settings(enable_result: object, channel_result: object) -> dict[str, object]:
    if ((enable_result is not None and
         (not isinstance(enable_result, Mapping) or len(enable_result) > 1)) or
        (channel_result is not None and
         (not isinstance(channel_result, Mapping) or len(channel_result) > 1))):
        raise ControllerTryBetaError("result_invalid")

    partial = enable_result is None or channel_result is None
    enabled: bool | None = None
    if isinstance(enable_result, Mapping):
        value = enable_result.get("enable")
        if value is None:
            partial = True
        elif type(value) is not bool:
            raise ControllerTryBetaError("enable_invalid")
        else:
            enabled = value

    channel_name = "unknown"
    channel_code: int | None = None
    if isinstance(channel_result, Mapping):
        value = channel_result.get("channel")
        if value is None:
            partial = True
        elif type(value) is not int or not 0 <= value < (1 << 31):
            raise ControllerTryBetaError("channel_invalid")
        else:
            channel_code = value
            channel_name = {0: "stable", 1: "release_candidate", 2: "beta"}.get(
                value, "unknown")
            partial |= channel_name == "unknown"

    return {
        "preview_firmware_enabled": enabled,
        "preview_firmware_channel": channel_name,
        "preview_firmware_channel_code": channel_code,
        "partial": partial,
    }
