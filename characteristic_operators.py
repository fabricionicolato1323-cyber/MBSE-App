from __future__ import annotations

from typing import Any

from graph_model import OAGraph


NUMBER_OPERATORS = {"=", ">", ">=", "<", "<="}
LOWER_BOUND_OPERATORS = {">", ">="}
UPPER_BOUND_OPERATORS = {"<", "<="}
PERCENTAGE_VALUE_TYPES = {"percentage", "percentage_range"}

_OPERATOR_ALIASES = {
    "≥": ">=",
    "≤": "<=",
}
_OPERATOR_SYMBOLS = {
    "=": "=",
    ">": ">",
    ">=": "≥",
    "<": "<",
    "<=": "≤",
}

_BASE_NORMALIZE_CHARACTERISTIC = OAGraph._normalize_characteristic
_BASE_FORMAT_CHARACTERISTIC = OAGraph._format_characteristic
_INSTALLED = False


def _normalize_operator(
    raw: Any,
    *,
    allowed: set[str],
    default: str,
    label: str,
) -> tuple[bool, str, str]:
    text = str(raw if raw is not None else default).strip()
    text = _OPERATOR_ALIASES.get(text, text)
    if text not in allowed:
        return False, "", f"Unsupported {label} operator."
    return True, text, ""


def _base_compatible_characteristic(characteristic: dict) -> tuple[dict, str | None]:
    """Translate percentage types through the existing numeric normalizer.

    The base graph currently knows number/range/text. Percentage is intentionally
    kept as a distinct persisted type while reusing the same finite-number and
    range validation rules.
    """
    requested_type = str(characteristic.get("value_type", "")).strip().casefold()
    if requested_type == "percentage":
        translated = dict(characteristic)
        translated["value_type"] = "number"
        translated["unit"] = "%"
        return translated, "percentage"
    if requested_type == "percentage_range":
        translated = dict(characteristic)
        translated["value_type"] = "range"
        translated["unit"] = "%"
        return translated, "percentage_range"
    return characteristic, None


def _operator_aware_normalize(characteristic: dict) -> tuple[bool, dict, str]:
    base_input, percentage_type = _base_compatible_characteristic(characteristic)
    ok, normalized, error = _BASE_NORMALIZE_CHARACTERISTIC(base_input)
    if not ok:
        return ok, normalized, error

    if percentage_type:
        normalized["value_type"] = percentage_type
        normalized["unit"] = "%"

    value_type = normalized.get("value_type")
    if value_type in {"number", "percentage"}:
        valid, operator, operator_error = _normalize_operator(
            characteristic.get("operator"),
            allowed=NUMBER_OPERATORS,
            default="=",
            label="numeric comparison",
        )
        if not valid:
            return False, {}, operator_error
        normalized["operator"] = operator

    elif value_type in {"range", "percentage_range"}:
        valid, lower_operator, operator_error = _normalize_operator(
            characteristic.get("lower_operator"),
            allowed=LOWER_BOUND_OPERATORS,
            default=">=",
            label="lower-bound",
        )
        if not valid:
            return False, {}, operator_error

        valid, upper_operator, operator_error = _normalize_operator(
            characteristic.get("upper_operator"),
            allowed=UPPER_BOUND_OPERATORS,
            default="<=",
            label="upper-bound",
        )
        if not valid:
            return False, {}, operator_error

        lower = normalized["lower_bound"]
        upper = normalized["upper_bound"]
        if lower == upper and (lower_operator == ">" or upper_operator == "<"):
            return (
                False,
                {},
                "Equal range bounds are only valid when both boundaries are inclusive.",
            )

        normalized["lower_operator"] = lower_operator
        normalized["upper_operator"] = upper_operator

    return True, normalized, ""


def _operator_aware_format(characteristic: dict) -> str:
    name = characteristic.get("name", "Characteristic")
    kind = characteristic.get("value_type")

    if kind in {"number", "percentage"}:
        _, operator, _ = _normalize_operator(
            characteristic.get("operator"),
            allowed=NUMBER_OPERATORS,
            default="=",
            label="numeric comparison",
        )
        symbol = _OPERATOR_SYMBOLS.get(operator, operator)
        value = characteristic.get("value", "")
        unit = "%" if kind == "percentage" else characteristic.get("unit", "")
        suffix = "%" if unit == "%" else (f" {unit}" if unit else "")
        return f"{name}: {symbol} {value}{suffix}"

    if kind in {"range", "percentage_range"}:
        _, lower_operator, _ = _normalize_operator(
            characteristic.get("lower_operator"),
            allowed=LOWER_BOUND_OPERATORS,
            default=">=",
            label="lower-bound",
        )
        _, upper_operator, _ = _normalize_operator(
            characteristic.get("upper_operator"),
            allowed=UPPER_BOUND_OPERATORS,
            default="<=",
            label="upper-bound",
        )
        lower_relation = "<" if lower_operator == ">" else "≤"
        upper_relation = "<" if upper_operator == "<" else "≤"
        lower = characteristic.get("lower_bound", "")
        upper = characteristic.get("upper_bound", "")
        unit = "%" if kind == "percentage_range" else characteristic.get("unit", "")

        if unit == "%":
            return (
                f"{name}: {lower}% {lower_relation} value "
                f"{upper_relation} {upper}%"
            )

        suffix = f" {unit}" if unit else ""
        return (
            f"{name}: {lower} {lower_relation} value "
            f"{upper_relation} {upper}{suffix}"
        )

    return _BASE_FORMAT_CHARACTERISTIC(characteristic)


def install_characteristic_operator_support() -> None:
    """Extend the characteristic schema with comparisons and percentages.

    Existing saved characteristics remain valid:
    - a number without an operator is interpreted as exact (=);
    - a range without boundary operators is interpreted as inclusive (>= / <=).

    Percentage characteristics reuse numeric validation but remain distinct
    persisted types and always use the percent sign as their unit. Values are
    percentage points (25 means 25%), and are not artificially limited to 0..100.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    OAGraph._normalize_characteristic = staticmethod(_operator_aware_normalize)
    OAGraph._format_characteristic = staticmethod(_operator_aware_format)
    _INSTALLED = True
