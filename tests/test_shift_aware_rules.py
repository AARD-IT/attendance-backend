from unittest.mock import patch

from app.services.dashboard_analytics_service import DashboardAnalyticsService
from app.services.shift_rules import get_shift_rule
from app.services.attendance_shift_engine import AttendanceShiftEngine


def test_get_shift_rule_normalizes_shift_2_case_insensitively():
    rule = get_shift_rule(" shift 2 ")

    assert rule["login_cutoff"] == "14:35"
    assert rule["logout_cutoff"] == "22:00"


def test_classify_record_uses_shift_assignment_for_login_and_logout_thresholds():
    profile = [{"id": "emp-1", "full_name": "Rafiq", "department": "Ops"}]
    assignments = [
        {
            "id": "shift-1",
            "employee_id": "emp-1",
            "minerva_employee_id": "M-1",
            "employee_name": "Rafiq",
            "employee_email": "rafiq@company.com",
            "cc_email": "manager@company.com",
            "shift_type": "Shift 2",
            "effective_from": "2026-06-01",
            "effective_to": "2026-06-30",
            "is_active": True,
        }
    ]
    record = {
        "id": "rec-1",
        "employee_id": "emp-1",
        "attendance_date": "2026-06-10",
        "first_punch": "2026-06-10T14:40:00+00:00",
        "last_punch": "2026-06-10T21:50:00+00:00",
        "total_hours": 7.0,
    }

    side_effect = lambda table: profile if table == "profiles" else assignments if table in ("employee_shift_assignments", "shift_assignments") else [record]
    with patch.object(DashboardAnalyticsService, "_fetch_records", side_effect=side_effect), \
         patch.object(AttendanceShiftEngine, "_fetch_records", side_effect=side_effect):
        classification = DashboardAnalyticsService._classify_record(record)

    assert classification["is_late"] is True
    assert classification["is_early_out"] is True


def test_classify_record_resolves_shift_assignment_by_employee_name_and_effective_date():
    profile = [{"id": "emp-1", "full_name": "Rafiq", "department": "Ops"}]
    assignments = [
        {
            "id": "shift-1",
            "employee_id": "other-emp",
            "minerva_employee_id": "M-99",
            "employee_name": "Rafiq",
            "shift_type": "Shift 2",
            "effective_from": "2026-06-01",
            "effective_to": "2026-06-30",
            "is_active": True,
        }
    ]
    record = {
        "id": "rec-3",
        "employee_id": "emp-1",
        "attendance_date": "2026-06-10",
        "first_punch": "2026-06-10T14:40:00+00:00",
        "last_punch": "2026-06-10T21:50:00+00:00",
        "total_hours": 7.0,
    }

    side_effect = lambda table: profile if table == "profiles" else assignments if table in ("employee_shift_assignments", "shift_assignments") else [record]
    with patch.object(DashboardAnalyticsService, "_fetch_records", side_effect=side_effect), \
         patch.object(AttendanceShiftEngine, "_fetch_records", side_effect=side_effect):
        classification = DashboardAnalyticsService._classify_record(record)

    assert classification["is_late"] is True
    assert classification["is_early_out"] is True


def test_classify_record_treats_lowercase_shift_2_as_shift_2_rules():
    profile = [{"id": "emp-1", "full_name": "Rafiq", "department": "Ops"}]
    assignments = [
        {
            "id": "shift-1",
            "employee_id": "emp-1",
            "shift_type": "shift 2",
            "effective_from": "2026-06-01",
            "effective_to": "2026-06-30",
            "is_active": True,
        }
    ]
    record = {
        "id": "rec-2",
        "employee_id": "emp-1",
        "attendance_date": "2026-06-10",
        "first_punch": "2026-06-10T10:38:00+00:00",
        "last_punch": "2026-06-10T20:42:00+00:00",
        "total_hours": 7.0,
    }

    side_effect = lambda table: profile if table == "profiles" else assignments if table in ("employee_shift_assignments", "shift_assignments") else [record]
    with patch.object(DashboardAnalyticsService, "_fetch_records", side_effect=side_effect), \
         patch.object(AttendanceShiftEngine, "_fetch_records", side_effect=side_effect):
        classification = DashboardAnalyticsService._classify_record(record)

    assert classification["is_late"] is False
    assert classification["is_early_out"] is True
