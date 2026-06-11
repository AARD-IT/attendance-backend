"""Analytics helpers for the Phase 3 dashboard."""

import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.services.attendance_shift_engine import AttendanceShiftEngine
from app.services.shift_rules import get_shift_rule, minutes_since_midnight, normalize_shift_type


HEADERS = {
    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}


class DashboardAnalyticsService:
    """Build CEO dashboard analytics from existing Supabase tables."""

    @staticmethod
    def _default_login_threshold() -> datetime.time:
        return datetime.strptime("10:35", "%H:%M").time()

    @staticmethod
    def _default_logout_threshold() -> datetime.time:
        return datetime.strptime("18:00", "%H:%M").time()

    @staticmethod
    def _normalize_lookup_value(value: Any) -> str:
        return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())

    @staticmethod
    def _get_shift_assignment(employee_id: str, attendance_date: str, employee_name: str | None = None) -> Dict[str, Any] | None:
        return AttendanceShiftEngine.resolve_shift_assignment({
            "employee_id": employee_id,
            "employee_name": employee_name,
            "attendance_date": attendance_date,
        })

    @staticmethod
    def _shift_thresholds(record: Dict[str, Any]) -> Dict[str, Any]:
        attendance_date = str(record.get("attendance_date") or "")
        employee_id = str(record.get("employee_id") or "")
        employee_name = str(record.get("employee_name") or "") or None
        assignment = DashboardAnalyticsService._get_shift_assignment(employee_id, attendance_date, employee_name=employee_name) if employee_id else None
        shift_type = normalize_shift_type((assignment or {}).get("shift_type") or "Shift 1")
        rule = get_shift_rule(shift_type)
        return {
            "login_cutoff": minutes_since_midnight(rule.get("login_cutoff", "10:35")),
            "logout_cutoff": minutes_since_midnight(rule.get("logout_cutoff", "18:00")),
            "login_threshold": datetime.strptime(rule.get("login_cutoff", "10:35"), "%H:%M").time(),
            "logout_threshold": datetime.strptime(rule.get("logout_cutoff", "18:00"), "%H:%M").time(),
            "shift_type": shift_type,
        }

    @staticmethod
    def _fetch_records(table: str) -> List[Dict[str, Any]]:
        url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/{table}"
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=HEADERS)
            if response.status_code != 200:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch {table}")
            return response.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Supabase request failed") from exc

    @staticmethod
    def _profile_map(profiles: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        return {str(profile.get("id")): profile for profile in profiles}

    @staticmethod
    def _is_minerva_employee(profile: Dict[str, Any]) -> bool:
        role = str(profile.get("role") or "").strip().upper()
        has_emp_code = bool(str(profile.get("emp_code") or "").strip())
        has_minerva_id = bool(str(profile.get("minerva_employee_id") or "").strip())
        return role == "EMPLOYEE" and (has_emp_code or has_minerva_id)

    @staticmethod
    def _display_employee_code(profile: Dict[str, Any]) -> str:
        return str(profile.get("minerva_employee_id") or profile.get("emp_code") or profile.get("employee_code") or profile.get("id") or "").strip()

    @staticmethod
    def _normalize_status(value: Any) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            text = str(value).strip().replace("Z", "+00:00")
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    @staticmethod
    def _filter_records_for_month(records: List[Dict[str, Any]], month: int | None = None, year: int | None = None) -> List[Dict[str, Any]]:
        if month is None:
            month = datetime.now().month
        if year is None:
            year = datetime.now().year

        return [
            record for record in records
            if str(record.get("attendance_date", "")).startswith(f"{year:04d}-{month:02d}-")
        ]

    @staticmethod
    def _format_time(value: Any) -> str:
        parsed = DashboardAnalyticsService._parse_timestamp(value)
        if parsed is None:
            return str(value or "")

        normalized = parsed.replace(tzinfo=None)
        return normalized.strftime("%H:%M")

    @staticmethod
    def _average_time(values: List[Any]) -> str:
        if not values:
            return "--"

        minutes = [v.hour * 60 + v.minute + (v.second / 60) for v in values]
        if len(minutes) == 1:
            return f"{int(minutes[0]) // 60:02d}:{int(minutes[0]) % 60:02d}"

        mean_x = sum(math.cos(2 * math.pi * minute / 1440) for minute in minutes) / len(minutes)
        mean_y = sum(math.sin(2 * math.pi * minute / 1440) for minute in minutes) / len(minutes)

        if mean_x == 0 and mean_y == 0:
            avg_minutes = int(sum(minutes) / len(minutes))
        else:
            angle = math.atan2(mean_y, mean_x)
            avg_minutes = round((angle / (2 * math.pi)) * 1440) % 1440

        total_minutes = int(avg_minutes)
        return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"

    @staticmethod
    def _working_hours_from_record(record: Dict[str, Any]) -> float:
        total_hours = float(record.get("total_hours") or 0)
        if total_hours > 0:
            return total_hours

        first_punch = record.get("first_punch")
        last_punch = record.get("last_punch")

        if first_punch and last_punch:
            try:
                start = datetime.fromisoformat(str(first_punch).replace("Z", "+00:00")).astimezone()
                end = datetime.fromisoformat(str(last_punch).replace("Z", "+00:00")).astimezone()
                return max(0.0, (end - start).total_seconds() / 3600)
            except ValueError:
                pass

        return total_hours

    @staticmethod
    def _is_missing_punch(record: Dict[str, Any]) -> bool:
        first_punch = record.get("first_punch")
        last_punch = record.get("last_punch")
        total_hours = float(record.get("total_hours") or 0)

        if first_punch and last_punch:
            try:
                start = DashboardAnalyticsService._parse_timestamp(first_punch)
                end = DashboardAnalyticsService._parse_timestamp(last_punch)
                if start is not None and end is not None and start == end:
                    return True
            except ValueError:
                pass

        return total_hours <= 0

    @staticmethod
    def _classify_record(record: Dict[str, Any]) -> Dict[str, Any]:
        classification = AttendanceShiftEngine.classify_record(record)
        if classification.get("status") == "MISSING_PUNCH":
            return classification

        first_punch = DashboardAnalyticsService._parse_timestamp(record.get("first_punch"))
        last_punch = DashboardAnalyticsService._parse_timestamp(record.get("last_punch"))
        thresholds = DashboardAnalyticsService._shift_thresholds(record)

        classification["is_late"] = bool(first_punch and first_punch.replace(tzinfo=None).time() > thresholds["login_threshold"])
        classification["is_early_out"] = bool(last_punch and last_punch.replace(tzinfo=None).time() < thresholds["logout_threshold"])

        if classification["is_late"] and classification["is_early_out"]:
            classification["status"] = "LATE_EARLY_OUT"
        elif classification["is_late"]:
            classification["status"] = "LATE"
        elif classification["is_early_out"]:
            classification["status"] = "EARLY_OUT"
        else:
            classification["status"] = "PRESENT"

        return classification

    @staticmethod
    def get_summary(month: int | None = None, year: int | None = None) -> Dict[str, Any]:
        profiles = DashboardAnalyticsService._fetch_records("profiles")
        records = DashboardAnalyticsService._fetch_records("attendance_records")

        today = date.today().isoformat()
        today_records = [record for record in records if str(record.get("attendance_date")) == today]

        employee_profiles = [profile for profile in profiles if DashboardAnalyticsService._is_minerva_employee(profile)]

        present = sum(1 for record in today_records if DashboardAnalyticsService._normalize_status(record.get("status")) == "PRESENT")
        absent = sum(1 for record in today_records if DashboardAnalyticsService._normalize_status(record.get("status")) == "ABSENT")
        half_day = sum(1 for record in today_records if DashboardAnalyticsService._normalize_status(record.get("status")) == "HALF_DAY")
        leave = sum(1 for record in today_records if DashboardAnalyticsService._normalize_status(record.get("status")) == "LEAVE")

        late_arrivals = 0
        for record in today_records:
            first_punch = record.get("first_punch")
            if not first_punch:
                continue
            try:
                parsed = DashboardAnalyticsService._parse_timestamp(first_punch)
                if parsed is not None:
                    punch_time = parsed.replace(tzinfo=None).time()
                    if punch_time > DashboardAnalyticsService._shift_thresholds(record)["login_threshold"]:
                        late_arrivals += 1
            except ValueError:
                continue

        total_employees = len(employee_profiles)
        attendance_percentage = 0
        if total_employees:
            attendance_percentage = round(((present + (half_day * 0.5)) / total_employees) * 100, 2)

        return {
            "total_employees": total_employees,
            "present_today": present,
            "absent_today": absent,
            "late_arrivals": late_arrivals,
            "half_day": half_day,
            "leave": leave,
            "attendance_percentage": attendance_percentage,
        }

    @staticmethod
    def get_trends(month: int | None = None, year: int | None = None) -> List[Dict[str, Any]]:
        records = DashboardAnalyticsService._fetch_records("attendance_records")

        if month is None:
            month = datetime.now().month
        if year is None:
            year = datetime.now().year

        month_records = DashboardAnalyticsService._filter_records_for_month(records, month=month, year=year)
        month_start = datetime(year, month, 1)
        month_end = (month_start.replace(month=month + 1, day=1) if month < 12 else datetime(year + 1, 1, 1)) - timedelta(days=1)
        trend = []

        current_day = month_start.date()
        while current_day <= month_end.date():
            day = current_day.isoformat()
            day_records = [record for record in month_records if str(record.get("attendance_date")) == day]
            present = sum(1 for record in day_records if DashboardAnalyticsService._normalize_status(record.get("status")) == "PRESENT")
            absent = sum(1 for record in day_records if DashboardAnalyticsService._normalize_status(record.get("status")) == "ABSENT")
            late_arrivals = 0
            for record in day_records:
                first_punch = record.get("first_punch")
                if not first_punch:
                    continue
                try:
                    parsed = DashboardAnalyticsService._parse_timestamp(first_punch)
                    if parsed is not None:
                        punch_time = parsed.replace(tzinfo=None).time()
                        if punch_time > DashboardAnalyticsService._shift_thresholds(record)["login_threshold"]:
                            late_arrivals += 1
                except ValueError:
                    continue

            trend.append({
                "date": day,
                "present": present,
                "absent": absent,
                "late_arrivals": late_arrivals,
            })
            current_day += timedelta(days=1)

        return trend

    @staticmethod
    def get_departments() -> List[Dict[str, Any]]:
        profiles = DashboardAnalyticsService._fetch_records("profiles")
        records = DashboardAnalyticsService._fetch_records("attendance_records")
        profile_map = DashboardAnalyticsService._profile_map(profiles)

        department_totals: Dict[str, Dict[str, Any]] = {}
        for record in records:
            employee = profile_map.get(str(record.get("employee_id")), {})
            department = str(employee.get("department") or "Unknown").strip() or "Unknown"
            status = DashboardAnalyticsService._normalize_status(record.get("status"))
            entry = department_totals.setdefault(department, {"total": 0, "weighted": 0.0})
            entry["total"] += 1
            if status in {"PRESENT", "HALF_DAY"}:
                entry["weighted"] += 1.0 if status == "PRESENT" else 0.5

        result = []
        for department, values in department_totals.items():
            attendance_percentage = round((values["weighted"] / values["total"]) * 100, 2) if values["total"] else 0
            result.append({"department": department, "attendance_percentage": attendance_percentage})

        return sorted(result, key=lambda item: item["attendance_percentage"], reverse=True)

    @staticmethod
    def _monthly_employee_summary(employee_id: str, records: List[Dict[str, Any]], profile_map: Dict[str, Dict[str, Any]], month: int, year: int) -> Dict[str, Any]:
        employee_records = [
            record for record in records
            if str(record.get("employee_id")) == employee_id and
            str(record.get("attendance_date", "")).startswith(f"{year:04d}-{month:02d}-")
        ]

        login_times = []
        logout_times = []
        total_hours = 0.0
        late_count = 0
        login_deviation = 0
        logout_deviation = 0
        missing_punches = 0

        for record in employee_records:
            classification = DashboardAnalyticsService._classify_record(record)
            if classification["is_missing_punch"]:
                missing_punches += 1
                continue

            first_punch = DashboardAnalyticsService._parse_timestamp(record.get("first_punch"))
            last_punch = DashboardAnalyticsService._parse_timestamp(record.get("last_punch"))

            total_hours += DashboardAnalyticsService._working_hours_from_record(record)

            if first_punch is not None:
                login_times.append(first_punch.replace(tzinfo=None).time())
                if classification["is_late"]:
                    late_count += 1
                    login_deviation += 1

            if last_punch is not None:
                logout_times.append(last_punch.replace(tzinfo=None).time())
                if classification["is_early_out"]:
                    logout_deviation += 1

        total_deviations = login_deviation + logout_deviation
        employee = profile_map.get(employee_id, {})

        return {
            "employee_id": employee_id,
            "employee_name": employee.get("full_name") or "Unknown Employee",
            "employee_code": DashboardAnalyticsService._display_employee_code(employee) or "Unknown",
            "department": employee.get("department") or "Unknown",
            "average_working_hours": round(total_hours / max(len(employee_records), 1), 2),
            "average_login_time": DashboardAnalyticsService._average_time(login_times),
            "average_logout_time": DashboardAnalyticsService._average_time(logout_times),
            "total_late_count": late_count,
            "login_deviation": login_deviation,
            "logout_deviation": logout_deviation,
            "escalations": total_deviations // 3,
            "total_deviations": total_deviations,
            "missing_punches": missing_punches,
            "total_records": len(employee_records),
        }

    @staticmethod
    def get_employees(month: int | None = None, year: int | None = None) -> List[Dict[str, Any]]:
        profiles = DashboardAnalyticsService._fetch_records("profiles")
        records = DashboardAnalyticsService._fetch_records("attendance_records")
        profile_map = DashboardAnalyticsService._profile_map(profiles)

        if month is None:
            month = datetime.now().month
        if year is None:
            year = datetime.now().year

        month_records = DashboardAnalyticsService._filter_records_for_month(records, month=month, year=year)

        unique_employee_ids = sorted({str(record.get("employee_id")) for record in month_records if record.get("employee_id")})
        rows = [
            DashboardAnalyticsService._monthly_employee_summary(employee_id, records, profile_map, month, year)
            for employee_id in unique_employee_ids
        ]

        return sorted(rows, key=lambda item: item["employee_name"].lower())

    @staticmethod
    def get_working_hours(month: int | None = None, year: int | None = None) -> List[Dict[str, Any]]:
        profiles = DashboardAnalyticsService._fetch_records("profiles")
        records = DashboardAnalyticsService._fetch_records("attendance_records")
        profile_map = DashboardAnalyticsService._profile_map(profiles)

        month_records = DashboardAnalyticsService._filter_records_for_month(records, month=month, year=year)

        grouped: Dict[str, Dict[str, Any]] = {}
        for record in month_records:
            employee_id = str(record.get("employee_id"))
            employee = profile_map.get(employee_id, {})
            entry = grouped.setdefault(employee_id, {"employee_name": employee.get("full_name") or "Unknown Employee", "total_hours": 0.0, "records": 0})
            entry["total_hours"] += DashboardAnalyticsService._working_hours_from_record(record)
            entry["records"] += 1

        return [
            {
                "employee_name": item["employee_name"],
                "total_hours": round(item["total_hours"], 2),
                "average_daily_hours": round(item["total_hours"] / max(item["records"], 1), 2),
            }
            for item in sorted(grouped.values(), key=lambda item: item["total_hours"], reverse=True)
        ]

    @staticmethod
    def get_employee_monthly_attendance(employee_id: str, month: int | None = None, year: int | None = None) -> Dict[str, Any]:
        profiles = DashboardAnalyticsService._fetch_records("profiles")
        records = DashboardAnalyticsService._fetch_records("attendance_records")
        profile_map = DashboardAnalyticsService._profile_map(profiles)

        if month is None:
            month = datetime.now().month
        if year is None:
            year = datetime.now().year

        employee_records = [
            record for record in records
            if str(record.get("employee_id")) == employee_id and
            str(record.get("attendance_date", "")).startswith(f"{year:04d}-{month:02d}-")
        ]

        login_times = []
        logout_times = []
        missing_punches = 0
        login_deviation = 0
        logout_deviation = 0

        for record in employee_records:
            classification = DashboardAnalyticsService._classify_record(record)
            if classification["is_missing_punch"]:
                missing_punches += 1
                continue

            first_punch = DashboardAnalyticsService._parse_timestamp(record.get("first_punch"))
            last_punch = DashboardAnalyticsService._parse_timestamp(record.get("last_punch"))
            if first_punch is not None:
                login_times.append(first_punch.replace(tzinfo=None).time())
                if classification["is_late"]:
                    login_deviation += 1
            if last_punch is not None:
                logout_times.append(last_punch.replace(tzinfo=None).time())
                if classification["is_early_out"]:
                    logout_deviation += 1

        total_hours = sum(DashboardAnalyticsService._working_hours_from_record(record) for record in employee_records)
        total_deviations = login_deviation + logout_deviation

        return {
            "month": datetime(year, month, 1).strftime("%B"),
            "year": year,
            "total_working_days": len(employee_records),
            "present_days": len(employee_records) - missing_punches,
            "login_deviation": login_deviation,
            "logout_deviation": logout_deviation,
            "missing_punches": missing_punches,
            "total_deviations": total_deviations,
            "escalations": total_deviations // 3,
            "average_login_time": DashboardAnalyticsService._average_time(login_times),
            "average_logout_time": DashboardAnalyticsService._average_time(logout_times),
            "average_working_hours": f"{(total_hours / max(len(employee_records), 1)):.2f}".rstrip('0').rstrip('.'),
            "employee": profile_map.get(employee_id, {}),
        }

    @staticmethod
    def get_employee_detail(employee_id: str, month: int | None = None, year: int | None = None) -> Dict[str, Any]:
        profiles = DashboardAnalyticsService._fetch_records("profiles")
        records = DashboardAnalyticsService._fetch_records("attendance_records")
        profile_map = DashboardAnalyticsService._profile_map(profiles)
        employee = profile_map.get(employee_id, {})

        if month is None:
            month = datetime.now().month
        if year is None:
            year = datetime.now().year

        employee_records = [
            record for record in records
            if str(record.get("employee_id")) == employee_id and
            str(record.get("attendance_date", "")).startswith(f"{year:04d}-{month:02d}-")
        ]
        late_count = 0
        login_times = []
        logout_times = []
        total_hours = 0.0

        for record in employee_records:
            total_hours += DashboardAnalyticsService._working_hours_from_record(record)
            classification = DashboardAnalyticsService._classify_record(record)

            first_punch = record.get("first_punch")
            if first_punch:
                try:
                    parsed = DashboardAnalyticsService._parse_timestamp(first_punch)
                    if parsed is not None:
                        punch_time = parsed.replace(tzinfo=None).time()
                        login_times.append(punch_time)
                        if classification["is_late"] and not classification["is_missing_punch"]:
                            late_count += 1
                except ValueError:
                    pass
            last_punch = record.get("last_punch")
            if last_punch:
                try:
                    parsed = DashboardAnalyticsService._parse_timestamp(last_punch)
                    if parsed is not None:
                        logout_times.append(parsed.replace(tzinfo=None).time())
                except ValueError:
                    pass

        avg_login = DashboardAnalyticsService._average_time(login_times)
        avg_logout = DashboardAnalyticsService._average_time(logout_times)
        avg_hours = total_hours / max(len(employee_records), 1)

        rows = []
        for record in sorted(employee_records, key=lambda item: str(item.get("attendance_date", "")), reverse=True):
            classification = DashboardAnalyticsService._classify_record(record)
            first_punch = DashboardAnalyticsService._format_time(record.get("first_punch"))
            last_punch = DashboardAnalyticsService._format_time(record.get("last_punch"))
            rows.append({
                "id": record.get("id"),
                "name": employee.get("full_name") or "Unknown Employee",
                "date": str(record.get("attendance_date")),
                "weekday": datetime.strptime(str(record.get("attendance_date")), "%Y-%m-%d").strftime("%A"),
                "first_punch": first_punch,
                "last_punch": last_punch,
                "total_time": float(record.get("total_hours") or 0),
                "late": "YES" if classification["is_late"] else "NO",
                "status": classification["status"],
                "shift_type": classification.get("shift_type") or record.get("shift_type") or record.get("shift_name") or "Shift 1",
                "shift_name": record.get("shift_name") or classification.get("shift_type") or "Shift 1",
                "is_missing_punch": classification["is_missing_punch"],
                "is_late": classification["is_late"],
                "is_early_out": classification["is_early_out"],
            })

        return {
            "employee_id": employee_id,
            "employee_name": employee.get("full_name") or "Unknown Employee",
            "employee_code": DashboardAnalyticsService._display_employee_code(employee) or "Unknown",
            "average_login": avg_login,
            "average_logout": avg_logout,
            "average_hours": round(avg_hours, 2),
            "total_late_count": late_count,
            "records": rows,
        }

    @staticmethod
    def get_live_feed(month: int | None = None, year: int | None = None) -> List[Dict[str, Any]]:
        profiles = DashboardAnalyticsService._fetch_records("profiles")
        records = DashboardAnalyticsService._fetch_records("attendance_records")
        profile_map = DashboardAnalyticsService._profile_map(profiles)

        events = []
        for record in sorted(records, key=lambda item: str(item.get("attendance_date", "")), reverse=True)[:40]:
            employee = profile_map.get(str(record.get("employee_id")), {})
            first_punch = record.get("first_punch")
            last_punch = record.get("last_punch")
            classification = DashboardAnalyticsService._classify_record(record)
            attendance_date = str(record.get("attendance_date") or "")
            events.append({
                "employee_name": employee.get("full_name") or "Unknown Employee",
                "date": attendance_date,
                "check_in": DashboardAnalyticsService._format_time(first_punch) if first_punch else "--",
                "check_out": DashboardAnalyticsService._format_time(last_punch) if last_punch else "--",
                "status": classification["status"],
                "total_hours": round(DashboardAnalyticsService._working_hours_from_record(record), 2),
            })

        return sorted(events, key=lambda item: (item["date"], item["check_in"]), reverse=True)[:20]


analytics_service = DashboardAnalyticsService()
