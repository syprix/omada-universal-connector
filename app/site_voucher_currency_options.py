"""Bounded, redacted voucher currency short-code options."""
from __future__ import annotations

from collections import Counter
from typing import Any

MAX_CURRENCY_CODES = 100
MAX_CURRENCY_CODE_LENGTH = 32


class SiteVoucherCurrencyOptionsError(ValueError):
    """Raised when the documented currency response exceeds safe bounds."""


def _valid_code(value: Any, *, allow_empty: bool) -> bool:
    return (isinstance(value, str) and len(value) <= MAX_CURRENCY_CODE_LENGTH and
            (allow_empty or bool(value)) and
            all(character.isprintable() for character in value))


def project_site_voucher_currency_options(result: Any) -> dict[str, object]:
    if not isinstance(result, dict) or len(result) > 8:
        raise SiteVoucherCurrencyOptionsError("response_invalid")
    unknown_field_count = len(set(result) - {"currencyList", "selectedCurrency"})
    missing_field_count = 0
    invalid_value_count = 0
    duplicate_currency_code_count = 0
    currency_codes: list[str] = []
    currency_list_present = "currencyList" in result
    currency_list_row_count = 0
    if currency_list_present:
        rows = result["currencyList"]
        if not isinstance(rows, list) or len(rows) > MAX_CURRENCY_CODES:
            raise SiteVoucherCurrencyOptionsError("currency_list_invalid")
        currency_list_row_count = len(rows)
        valid_codes: list[str] = []
        for value in rows:
            if _valid_code(value, allow_empty=False):
                valid_codes.append(value)
            else:
                invalid_value_count += 1
        frequencies = Counter(valid_codes)
        duplicate_currency_code_count = sum(count > 1 for count in frequencies.values())
        currency_codes = [code for code in dict.fromkeys(valid_codes)
                          if frequencies[code] == 1]
    else:
        missing_field_count += 1

    selected_currency_field_present = "selectedCurrency" in result
    selected_currency_code: str | None = None
    if selected_currency_field_present:
        selected = result["selectedCurrency"]
        if _valid_code(selected, allow_empty=True):
            selected_currency_code = selected
        else:
            invalid_value_count += 1
    else:
        missing_field_count += 1

    data = {
        "currency_codes": currency_codes,
        "currency_code_count": len(currency_codes),
        "currency_list_present": currency_list_present,
        "currency_list_row_count": currency_list_row_count,
        "selected_currency_field_present": selected_currency_field_present,
        "selected_currency_code": selected_currency_code,
        "missing_field_count": missing_field_count,
        "invalid_value_count": invalid_value_count,
        "duplicate_currency_code_count": duplicate_currency_code_count,
        "unknown_field_count": unknown_field_count,
    }
    return {"data": data,
            "partial": bool(missing_field_count or invalid_value_count or
                            duplicate_currency_code_count or unknown_field_count)}
