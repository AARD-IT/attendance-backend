from unittest.mock import patch

from app.services.attendance_shift_engine import AttendanceShiftEngine
from app.services.dashboard_analytics_service import DashboardAnalyticsService


def test_missing_punch_overrides_shift_deviations():
    record = {
        "employee_id": "emp-1",
        "attendance_date": "2026-06-10",
        "first_punch": "2026-06-10T14:40:00+00:00",
        "last_punch": "2026-06-10T14:40:00+00:00",
        "total_hours": 0,
    }

    profile = [{"id": "emp-1", "full_name": "Rafiq"}]
    assignments = [
        {
            "employee_id": "emp-1",
            "shift_name": "Shift 2",
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
        }
    ]

    side_effect = lambda table: profile if table == "profiles" else assignments if table in ("shift_assignments", "employee_shift_assignments") else []
    with patch.object(AttendanceShiftEngine, "_fetch_records", side_effect=side_effect), \
         patch.object(DashboardAnalyticsService, "_fetch_records", side_effect=side_effect):
        classification = AttendanceShiftEngine.classify_record(record)

    assert classification["status"] == "MISSING_PUNCH"
    assert classification["is_late"] is False
    assert classification["is_early_out"] is False
    assert classification["shift_type"] == "Shift 2"
