"""Shift-aware attendance classification engine."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List

import httpx

from app.core.config import settings
from app.services.shift_rules import get_shift_rule, minutes_since_midnight, normalize_shift_type

HEADERS = {
    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}


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
    def _match_candidates(assignments: List[Dict[str, Any]], profiles: List[Dict[str, Any]], *, employee_id: str, employee_name: str | None, target_date: date) -> List[tuple[Dict[str, Any], Any, Any, str]]:
        profile_map = AttendanceShiftEngine._profile_map(profiles)
        employee_name_value = AttendanceShiftEngine._normalize_lookup(employee_name or profile_map.get(employee_id, {}).get("full_name"))
        employee_id_value = AttendanceShiftEngine._normalize_lookup(employee_id)

        candidates = []
        for assignment in assignments:
            assignment_employee_id = AttendanceShiftEngine._normalize_lookup(assignment.get("employee_id") or assignment.get("minerva_employee_id") or "")
            assignment_employee_name = AttendanceShiftEngine._normalize_lookup(assignment.get("employee_name") or profile_map.get(str(assignment.get("employee_id") or ""), {}).get("full_name") or "")
            shift_name = assignment.get("shift_name") or assignment.get("shift_type") or "Shift 1"
            start_date = assignment.get("start_date") or assignment.get("effective_from")
            end_date = assignment.get("end_date") or assignment.get("effective_to")

            matches_employee = bool(employee_id_value and (assignment_employee_id == employee_id_value or assignment_employee_id == AttendanceShiftEngine._normalize_lookup(str(assignment.get("minerva_employee_id") or ""))))
            if not matches_employee and employee_name_value and assignment_employee_name == employee_name_value:
                matches_employee = True
            if not matches_employee and employee_id_value and (AttendanceShiftEngine._normalize_lookup(assignment.get("employee_id") or "") == employee_id_value or AttendanceShiftEngine._normalize_lookup(assignment.get("minerva_employee_id") or "") == employee_id_value):
                matches_employee = True
            if not matches_employee:
                continue

            if assignment.get("is_active") is False:
                continue
            if start_date and target_date < datetime.fromisoformat(str(start_date)).date():
                continue
            if end_date and target_date > datetime.fromisoformat(str(end_date)).date():
                continue

            candidates.append((assignment, start_date, end_date, shift_name))

        return candidates

    @staticmethod
    def resolve_shift_assignment(record: Dict[str, Any]) -> Dict[str, Any] | None:
        employee_id = str(record.get("employee_id") or "")
        employee_name = str(record.get("employee_name") or "") or None
        attendance_date = str(record.get("attendance_date") or "")
        target_date = datetime.fromisoformat(attendance_date).date() if attendance_date else date.today()

        assignments = []
        profiles = []
        try:
            assignments = AttendanceShiftEngine._fetch_records("shift_assignments")
            profiles = AttendanceShiftEngine._fetch_records("profiles")
        except Exception:
            pass

        candidates = AttendanceShiftEngine._match_candidates(assignments, profiles, employee_id=employee_id, employee_name=employee_name, target_date=target_date)

        if not candidates:
            try:
                from app.services.dashboard_analytics_service import DashboardAnalyticsService

                assignments = DashboardAnalyticsService._fetch_records("employee_shift_assignments")
                profiles = DashboardAnalyticsService._fetch_records("profiles")
                if not assignments:
                    assignments = DashboardAnalyticsService._fetch_records("shift_assignments")
                candidates = AttendanceShiftEngine._match_candidates(assignments, profiles, employee_id=employee_id, employee_name=employee_name, target_date=target_date)
            except Exception:
                pass

        if not candidates:
            return None

        if not candidates:
            return None

        candidates.sort(key=lambda item: (datetime.fromisoformat(str(item[1])).date() if item[1] else date.min, datetime.fromisoformat(str(item[2])).date() if item[2] else date.max), reverse=True)
        assignment = candidates[0][0]
        assignment = dict(assignment)
        assignment.setdefault("shift_type", assignment.get("shift_name") or assignment.get("shift_type") or "Shift 1")
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
        total_hours = float(record.get("total_hours") or 0)

        assignment = AttendanceShiftEngine.resolve_shift_assignment(record)
        shift_type = normalize_shift_type((assignment or {}).get("shift_type") or "Shift 1")
        rule = get_shift_rule(shift_type)
        login_cutoff = minutes_since_midnight(rule.get("login_cutoff", "10:35"))
        logout_cutoff = minutes_since_midnight(rule.get("logout_cutoff", "18:00"))

        is_missing = (first_punch and last_punch and first_punch == last_punch) or total_hours <= 0
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
        else:
            status = "PRESENT"

        return {
            "status": status,
            "is_late": is_late,
            "is_early_out": is_early_out,
            "is_missing_punch": is_missing,
            "shift_type": shift_type,
            "login_cutoff": rule.get("login_cutoff", "10:35"),
            "logout_cutoff": rule.get("logout_cutoff", "18:00"),
        }
