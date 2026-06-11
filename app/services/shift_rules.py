"""Centralized shift rule configuration for attendance deviation logic."""

from datetime import datetime
from typing import Dict, Any

SHIFT_RULES: Dict[str, Dict[str, Any]] = {
    "Shift 1": {
        "login_cutoff": "10:35",
        "logout_cutoff": "18:00",
        "label": "Shift 1",
    },
    "Shift 2": {
        "login_cutoff": "14:35",
        "logout_cutoff": "22:00",
        "label": "Shift 2",
    },
}


def normalize_shift_type(shift_type: str) -> str:
    value = (shift_type or "Shift 1").strip().lower().replace("shift", "").replace("_", " ").replace("-", " ")
    value = " ".join(value.split())
    if value in {"1", "one"}:
        return "Shift 1"
    if value in {"2", "two"}:
        return "Shift 2"
    return "Shift 1"


def get_shift_rule(shift_type: str) -> Dict[str, Any]:
    normalized = normalize_shift_type(shift_type)
    return SHIFT_RULES.get(normalized, SHIFT_RULES["Shift 1"])


def minutes_since_midnight(value: str) -> int:
    parsed = datetime.strptime(value, "%H:%M").time()
    return parsed.hour * 60 + parsed.minute
