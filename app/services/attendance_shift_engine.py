"""Shift-aware attendance classification engine."""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any, Dict, List

import httpx

from app.core.config import settings
from app.services.shift_rules import (
    get_shift_rule,
    minutes_since_midnight,
    normalize_shift_type,
    resolve_shift_rule_from_assignment,
)
from app.services.shift_service import shift_service

HEADERS = {
    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}

# Cache to avoid duplicate database/network lookups during processing loops
_LOADED_CACHE: Dict[str, Any] = {}
CACHE_TTL = 30.0 # Cache for 30 seconds


class AttendanceShiftEngine:
    """Resolve shift rules per record and classify attendance."""

    @staticmethod
    def _normalize_lookup(value: Any) -> str:
        return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())

    @staticmethod
    def _fetch_records(table: str) -> List[Dict[str, Any]]:
        url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/{table}"
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=HEADERS)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to fetch {table}")
        return response.json()

    @staticmethod
    def _profile_map(profiles: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        return {str(profile.get("id")): profile for profile in profiles}

    @staticmethod
    def _assignment_dates(assignment: Dict[str, Any]) -> tuple[str | None, str | None]:
        start_date = assignment.get("start_date") or assignment.get("effective_from")
        end_date = assignment.get("end_date") or assignment.get("effective_to")
        return start_date, end_date

    @staticmethod
    def _match_candidates(assignments: List[Dict[str, Any]], profiles: List[Dict[str, Any]], *, employee_id: str, employee_name: str | None, target_date: date) -> List[tuple[Dict[str, Any], Any, Any, str]]:
        profile_map = AttendanceShiftEngine._profile_map(profiles)
        employee_name_value = AttendanceShiftEngine._normalize_lookup(employee_name or profile_map.get(employee_id, {}).get("full_name"))
        employee_id_value = AttendanceShiftEngine._normalize_lookup(employee_id)

        candidates = []
        for assignment in assignments:
            assignment_employee_id = AttendanceShiftEngine._normalize_lookup(assignment.get("employee_id") or assignment.get("minerva_employee_id") or "")
            assignment_employee_name = AttendanceShiftEngine._normalize_lookup(assignment.get("employee_name") or profile_map.get(str(assignment.get("employee_id") or ""), {}).get("full_name") or "")
            start_date, end_date = AttendanceShiftEngine._assignment_dates(assignment)
            shift_name = assignment.get("shift_name") or assignment.get("shift_type") or shift_service.get_default_shift().get("shift_name", "Shift 1")

            matches_employee = bool(employee_id_value and (assignment_employee_id == employee_id_value or assignment_employee_id == AttendanceShiftEngine._normalize_lookup(str(assignment.get("minerva_employee_id") or ""))))
            if not matches_employee and employee_name_value and assignment_employee_name == employee_name_value:
                matches_employee = True
            if not matches_employee and employee_id_value and (AttendanceShiftEngine._normalize_lookup(assignment.get("employee_id") or "") == employee_id_value or AttendanceShiftEngine._normalize_lookup(assignment.get("minerva_employee_id") or "") == employee_id_value):
                matches_employee = True
            if not matches_employee:
                continue

            active = assignment.get("status")
            if active is None:
                active = assignment.get("is_active", True)
            if active is False:
                continue
            if start_date and target_date < datetime.fromisoformat(str(start_date)).date():
                continue
            if end_date and target_date > datetime.fromisoformat(str(end_date)).date():
                continue

            candidates.append((assignment, start_date, end_date, shift_name))

        return candidates

    @staticmethod
    def _load_assignments_and_profiles() -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        global _LOADED_CACHE
        now = time.time()
        import os
        if "assignments" in _LOADED_CACHE and "profiles" in _LOADED_CACHE and now - _LOADED_CACHE.get("fetched_at", 0) < CACHE_TTL and not os.getenv("PYTEST_CURRENT_TEST"):
            return _LOADED_CACHE["assignments"], _LOADED_CACHE["profiles"]

        from app.services.dashboard_analytics_service import DashboardAnalyticsService

        assignments: List[Dict[str, Any]] = []
        profiles: List[Dict[str, Any]] = []
        seen_assignment_ids: set[str] = set()

        def _extend_assignments(rows: Any) -> None:
            if not isinstance(rows, list):
                return
            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_id = str(row.get("id") or "")
                dedupe_key = row_id or f"{row.get('employee_id')}-{row.get('start_date') or row.get('effective_from')}-{row.get('shift_type') or row.get('shift_name')}"
                if dedupe_key in seen_assignment_ids:
                    continue
                seen_assignment_ids.add(dedupe_key)
                assignments.append(row)

        for loader in (AttendanceShiftEngine._fetch_records, DashboardAnalyticsService._fetch_records):
            for table in ("employee_shift_assignments", "shift_assignments"):
                try:
                    _extend_assignments(loader(table))
                except Exception:
                    continue

        for loader in (AttendanceShiftEngine._fetch_records, DashboardAnalyticsService._fetch_records):
            try:
                fetched = loader("profiles")
                if isinstance(fetched, list) and fetched:
                    profiles = fetched
                    break
            except Exception:
                continue

        _LOADED_CACHE["assignments"] = assignments
        _LOADED_CACHE["profiles"] = profiles
        _LOADED_CACHE["fetched_at"] = now

        return assignments, profiles

    @staticmethod
    def resolve_shift_assignment(record: Dict[str, Any]) -> Dict[str, Any] | None:
        employee_id = str(record.get("employee_id") or "")
        employee_name = str(record.get("employee_name") or "") or None
        attendance_date = str(record.get("attendance_date") or "")
        target_date = datetime.fromisoformat(attendance_date).date() if attendance_date else date.today()

        assignments, profiles = AttendanceShiftEngine._load_assignments_and_profiles()

        if employee_id and not employee_name and profiles:
            employee_name = str(AttendanceShiftEngine._profile_map(profiles).get(employee_id, {}).get("full_name") or "") or None

        candidates = AttendanceShiftEngine._match_candidates(assignments, profiles, employee_id=employee_id, employee_name=employee_name, target_date=target_date)

        if not candidates:
            return None

        candidates.sort(key=lambda item: (datetime.fromisoformat(str(item[1])).date() if item[1] else date.min, datetime.fromisoformat(str(item[2])).date() if item[2] else date.max), reverse=True)
        assignment = dict(candidates[0][0])
        shift_type = assignment.get("shift_name") or assignment.get("shift_type")
        if assignment.get("shift_id"):
            shift = shift_service.get_shift(str(assignment["shift_id"]))
            if shift:
                assignment["shift_name"] = shift.get("shift_name")
                assignment["shift_type"] = shift.get("shift_name")
                assignment["shift"] = shift
        assignment.setdefault("shift_type", shift_type or shift_service.get_default_shift().get("shift_name", "Shift 1"))
        return assignment

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def classify_record(record: Dict[str, Any]) -> Dict[str, Any]:
        first_punch = AttendanceShiftEngine._parse_timestamp(record.get("first_punch"))
        last_punch = AttendanceShiftEngine._parse_timestamp(record.get("last_punch"))
        total_hours = float(record.get("total_hours") or record.get("working_hours") or 0)

        assignment = AttendanceShiftEngine.resolve_shift_assignment(record)
        rule = resolve_shift_rule_from_assignment(assignment)
        shift_type = normalize_shift_type(rule.get("shift_name") or rule.get("label") or "Shift 1")
        login_cutoff = minutes_since_midnight(rule.get("login_cutoff", "10:35"))
        logout_cutoff = minutes_since_midnight(rule.get("logout_cutoff", "18:00"))
        minimum_hours = float(rule.get("minimum_working_hours") or 8)

        is_missing = (first_punch and last_punch and first_punch == last_punch) or (first_punch and not last_punch) or total_hours <= 0
        is_late = bool(first_punch and first_punch.replace(tzinfo=None).time().hour * 60 + first_punch.replace(tzinfo=None).time().minute > login_cutoff)
        is_early_out = bool(last_punch and last_punch.replace(tzinfo=None).time().hour * 60 + last_punch.replace(tzinfo=None).time().minute < logout_cutoff)

        if is_missing:
            status = "MISSING_PUNCH"
            is_late = False
            is_early_out = False
        elif is_late and is_early_out:
            status = "LATE_EARLY_OUT"
        elif is_late:
            status = "LATE"
        elif is_early_out:
            status = "EARLY_OUT"
        elif total_hours >= minimum_hours or (first_punch and last_punch and total_hours > 0):
            status = "PRESENT"
        else:
            status = "ABSENT"

        return {
            "status": status,
            "is_late": is_late,
            "is_early_out": is_early_out,
            "is_missing_punch": is_missing,
            "shift_type": shift_type,
            "shift_id": rule.get("id"),
            "login_cutoff": rule.get("login_cutoff"),
            "logout_cutoff": rule.get("logout_cutoff"),
            "allowed_login_time": rule.get("allowed_login_time"),
            "minimum_logout_time": rule.get("minimum_logout_time"),
            "minimum_working_hours": minimum_hours,
            "assignment": assignment,
        }
