from __future__ import annotations

from typing import Any

from graph_model import OAGraph


NUMBER_OPERATORS = {"=", ">", ">=", "<", "<="}
LOWER_BOUND_OPERATORS = {">", ">="}
UPPER_BOUND_OPERATORS = {"<", "<="}

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


def _operator_aware_normalize(characteristic: dict) -> tuple[bool, dict, str]:
    ok, normalized, error = _BASE_NORMALIZE_CHARACTERISTIC(characteristic)
    if not ok:
        return ok, normalized, error

    value_type = normalized.get("value_type")
    if value_type == "number":
        valid, operator, operator_error = _normalize_operator(
            characteristic.get("operator"),
            allowed=NUMBER_OPERATORS,
            default="=",
            label="numeric comparison",
        )
        if not valid:
            return False, {}, operator_error
        normalized["operator"] = operator

    elif value_type == "range":
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

    if kind == "number":
        _, operator, _ = _normalize_operator(
            characteristic.get("operator"),
            allowed=NUMBER_OPERATORS,
            default="=",
            label="numeric comparison",
        )
        symbol = _OPERATOR_SYMBOLS.get(operator, operator)
        value = characteristic.get("value", "")
        unit = characteristic.get("unit", "")
        suffix = f" {unit}" if unit else ""
        return f"{name}: {symbol} {value}{suffix}"

    if kind == "range":
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
        unit = characteristic.get("unit", "")
        suffix = f" {unit}" if unit else ""
        return (
            f"{name}: {lower} {lower_relation} value "
            f"{upper_relation} {upper}{suffix}"
        )

    return _BASE_FORMAT_CHARACTERISTIC(characteristic)


def install_characteristic_operator_support() -> None:
    """Extend the existing characteristic schema with comparison operators.

    Existing saved characteristics remain valid:
    - a number without an operator is interpreted as exact (=);
    - a range without boundary operators is interpreted as inclusive (>= / <=).
    """

    global _INSTALLED
    if _INSTALLED:
        return
    OAGraph._normalize_characteristic = staticmethod(_operator_aware_normalize)
    OAGraph._format_characteristic = staticmethod(_operator_aware_format)
    _INSTALLED = True
