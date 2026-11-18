"""Redacted projection of documented per-band AP Advanced QoS fields."""
from __future__ import annotations


class ApQosError(ValueError):
    """The documented QoS response cannot be bounded or projected safely."""

    def __init__(self, code: str = "ap_qos_response_invalid") -> None:
        super().__init__(code)
        self.code = code


_BANDS = ("2g", "5g", "5g2", "6g")
_FIELDS = tuple(f"support{band}" for band in _BANDS) + tuple(
    f"deliveryEnable{band}" for band in _BANDS
)
_MAX_FIELDS = 32
_MAX_KEY_LENGTH = 128


def project_ap_qos(raw: object) -> dict[str, object]:
    """Project only the eight optional documented Boolean fields.

    Missing, invalid, or unknown fields mark the projection partial. Unknown
    names and all unrecognized values are excluded. ``support*`` reports the
    controller's per-band availability flag; it is not a guarantee that the
    QoS function is supported or enabled. The general projection preserves
    ``5g2`` as documented; the change-state validator uses that explicit flag
    to decide whether its delivery value is required.
    """
    if not isinstance(raw, dict) or len(raw) > _MAX_FIELDS:
        raise ApQosError()

    data: dict[str, bool] = {}
    missing: list[str] = []
    invalid: list[str] = []
    for field in _FIELDS:
        if field not in raw:
            missing.append(field)
        elif type(raw[field]) is bool:
            data[field] = raw[field]
        else:
            invalid.append(field)

    unknown_count = 0
    for key in raw:
        if not isinstance(key, str) or len(key) > _MAX_KEY_LENGTH:
            raise ApQosError()
        if key not in _FIELDS:
            unknown_count += 1

    return {
        "status": "ok",
        "resource": "ap_qos",
        "data": data,
        "partial": bool(missing or invalid or unknown_count),
        "missing_fields": missing,
        "invalid_fields": invalid,
        "unknown_field_count": unknown_count,
    }


def normalize_ap_qos_change_state(value: object) -> dict[str, bool]:
    """Validate the values needed to safely preserve supported bands.

    The source schemas make the delivery values optional. A value is required
    for a band only when its support flag says the device supports that band.
    The support flags themselves must all be present so a plan never guesses
    whether an omitted delivery value is applicable.
    """
    support_fields = {"support2g", "support5g", "support5g2", "support6g"}
    delivery_fields = {field for field in _FIELDS if field.startswith("deliveryEnable")}
    if (not isinstance(value, dict) or not set(value) <= set(_FIELDS) or
            any(type(item) is not bool for item in value.values()) or
            not support_fields <= set(value)):
        raise ApQosError("ap_qos_state_unavailable")

    if value["support5g2"] and not value["support5g"]:
        raise ApQosError("ap_qos_state_unavailable")
    required_delivery = set()
    if value["support2g"]:
        required_delivery.add("deliveryEnable2g")
    if value["support5g"]:
        required_delivery.add("deliveryEnable5g")
    if value["support5g2"]:
        required_delivery.add("deliveryEnable5g2")
    if value["support6g"]:
        required_delivery.add("deliveryEnable6g")
    if not required_delivery <= set(value):
        raise ApQosError("ap_qos_state_unavailable")

    # Preserve every supplied, documented value so the plan binds the exact
    # observed state while omitting values that the controller did not return.
    return {key: value[key] for key in sorted(support_fields | delivery_fields)
            if key in value}
