"""Dynamic shift rule resolution backed by the shifts table."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, Dict

from app.services.shift_service import shift_service


def normalize_shift_type(shift_type: str) -> str:
    value = (shift_type or "").strip().lower().replace("shift", "").replace("_", " ").replace("-", " ")
    value = " ".join(value.split())
    if value in {"1", "one"}:
        return "Shift 1"
    if value in {"2", "two"}:
        return "Shift 2"
    if not value:
        return shift_service.get_default_shift().get("shift_name", "Shift 1")
    return (shift_type or "").strip() or "Shift 1"


def _parse_time(value: Any) -> time:
    text = str(value or "00:00").strip()
    if len(text) == 5:
        text = f"{text}:00"
    parsed = datetime.strptime(text[:8], "%H:%M:%S").time()
    return parsed


def _format_hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def _shift_record(shift_type: str | None = None, shift_id: str | None = None) -> Dict[str, Any]:
    if shift_id:
        found = shift_service.get_shift(str(shift_id))
        if found:
            return found
    normalized = normalize_shift_type(str(shift_type or ""))
    found = shift_service.get_shift_by_name(normalized)
    if found:
        return found
    return shift_service.get_default_shift()


def compute_allowed_login_time(shift: Dict[str, Any]) -> time:
    start = _parse_time(shift.get("start_time"))
    grace = int(shift.get("grace_time_minutes") or 0)
    base = datetime.combine(datetime.today(), start)
    return (base + timedelta(minutes=grace)).time()


def compute_minimum_logout_time(shift: Dict[str, Any]) -> time:
    end = _parse_time(shift.get("end_time"))
    deviation = int(shift.get("logout_deviation_minutes") or 0)
    base = datetime.combine(datetime.today(), end)
    return (base - timedelta(minutes=deviation)).time()


def get_shift_rule(shift_type: str | None = None, *, shift_id: str | None = None) -> Dict[str, Any]:
    shift = _shift_record(shift_type, shift_id=shift_id)
    allowed_login = compute_allowed_login_time(shift)
    minimum_logout = compute_minimum_logout_time(shift)
    return {
        "id": shift.get("id"),
        "shift_name": shift.get("shift_name"),
        "label": shift.get("shift_name"),
        "start_time": _format_hhmm(_parse_time(shift.get("start_time"))),
        "end_time": _format_hhmm(_parse_time(shift.get("end_time"))),
        "grace_time_minutes": int(shift.get("grace_time_minutes") or 0),
        "minimum_working_hours": float(shift.get("minimum_working_hours") or 8),
        "login_deviation_minutes": int(shift.get("login_deviation_minutes") or 0),
        "logout_deviation_minutes": int(shift.get("logout_deviation_minutes") or 0),
        "login_cutoff": _format_hhmm(allowed_login),
        "logout_cutoff": _format_hhmm(minimum_logout),
        "allowed_login_time": _format_hhmm(allowed_login),
        "minimum_logout_time": _format_hhmm(minimum_logout),
        "status": bool(shift.get("status", True)),
    }


def minutes_since_midnight(value: str) -> int:
    parsed = datetime.strptime(value, "%H:%M").time()
    return parsed.hour * 60 + parsed.minute


def resolve_shift_rule_from_assignment(assignment: Dict[str, Any] | None) -> Dict[str, Any]:
    if not assignment:
        return get_shift_rule(None)
    shift_id = assignment.get("shift_id")
    shift_type = (
        assignment.get("shift_name")
        or assignment.get("shift_type")
        or assignment.get("shift")
    )
    if shift_id:
        return get_shift_rule(shift_type, shift_id=str(shift_id))
    embedded = assignment.get("shift") if isinstance(assignment.get("shift"), dict) else None
    if embedded:
        return get_shift_rule(embedded.get("shift_name"), shift_id=str(embedded.get("id") or "") or None)
    return get_shift_rule(str(shift_type or ""))
