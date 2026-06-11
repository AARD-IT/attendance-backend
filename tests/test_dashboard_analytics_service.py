from datetime import date, time
from unittest.mock import patch

from app.services.dashboard_analytics_service import DashboardAnalyticsService


def test_get_employee_monthly_attendance_summary_counts_month_specific_deviations():
    profiles = [{"id": "emp-1", "full_name": "Alex Stone"}]
    records = [
        {"id": "rec-1", "employee_id": "emp-1", "attendance_date": "2026-05-03", "first_punch": "2026-05-03T10:40:00+00:00", "last_punch": "2026-05-03T18:10:00+00:00", "total_hours": 7.5},
        {"id": "rec-2", "employee_id": "emp-1", "attendance_date": "2026-05-04", "first_punch": "2026-05-04T09:20:00+00:00", "last_punch": "2026-05-04T17:30:00+00:00", "total_hours": 8.0},
        {"id": "rec-3", "employee_id": "emp-1", "attendance_date": "2026-06-01", "first_punch": "2026-06-01T09:00:00+00:00", "last_punch": "2026-06-01T09:00:00+00:00", "total_hours": 0},
    ]

    with patch.object(DashboardAnalyticsService, "_fetch_records", side_effect=lambda table: profiles if table == "profiles" else records):
        result = DashboardAnalyticsService.get_employee_monthly_attendance("emp-1", month=5, year=2026)

    assert result["month"] == "May"
    assert result["year"] == 2026
    assert result["total_working_days"] == 2
    assert result["present_days"] == 2
    assert result["login_deviation"] == 1
    assert result["logout_deviation"] == 1
    assert result["missing_punches"] == 0
    assert result["total_deviations"] == 2
    assert result["escalations"] == 0
    assert result["average_login_time"] == "10:00"
    assert result["average_logout_time"] == "17:50"
    assert result["average_working_hours"] == "7.75"


def test_get_employee_monthly_attendance_marks_missing_punch_records():
    profiles = [{"id": "emp-1", "full_name": "Alex Stone"}]
    records = [
        {"id": "rec-1", "employee_id": "emp-1", "attendance_date": "2026-05-03", "first_punch": "2026-05-03T10:00:00+00:00", "last_punch": "2026-05-03T10:00:00+00:00", "total_hours": 0},
    ]

    with patch.object(DashboardAnalyticsService, "_fetch_records", side_effect=lambda table: profiles if table == "profiles" else records):
        result = DashboardAnalyticsService.get_employee_monthly_attendance("emp-1", month=5, year=2026)

    assert result["missing_punches"] == 1
    assert result["login_deviation"] == 0
    assert result["logout_deviation"] == 0
    assert result["total_deviations"] == 0
    assert result["escalations"] == 0


def test_average_time_handles_overnight_logout_values():
    values = [time(23, 30), time(0, 15), time(1, 0)]

    assert DashboardAnalyticsService._average_time(values) == "00:15"


def test_get_employees_returns_month_specific_analytics():
    profiles = [{"id": "emp-1", "full_name": "Alex Stone"}]
    records = [
        {"id": "rec-1", "employee_id": "emp-1", "attendance_date": "2026-05-03", "first_punch": "2026-05-03T10:40:00+00:00", "last_punch": "2026-05-03T18:10:00+00:00", "total_hours": 7.5},
        {"id": "rec-2", "employee_id": "emp-1", "attendance_date": "2026-06-01", "first_punch": "2026-06-01T09:00:00+00:00", "last_punch": "2026-06-01T18:00:00+00:00", "total_hours": 8.0},
    ]

    with patch.object(DashboardAnalyticsService, "_fetch_records", side_effect=lambda table: profiles if table == "profiles" else records):
        result = DashboardAnalyticsService.get_employees(month=5, year=2026)

    assert len(result) == 1
    assert result[0]["employee_name"] == "Alex Stone"
    assert result[0]["average_login_time"] == "10:40"
    assert result[0]["average_logout_time"] == "18:10"
    assert result[0]["total_late_count"] == 1
    assert result[0]["login_deviation"] == 1
    assert result[0]["logout_deviation"] == 0
    assert result[0]["escalations"] == 0


def test_get_employees_excludes_missing_punch_records_from_deviations():
    profiles = [{"id": "emp-1", "full_name": "Alex Stone"}]
    records = [
        {"id": "rec-1", "employee_id": "emp-1", "attendance_date": "2026-05-03", "first_punch": "2026-05-03T10:40:00+00:00", "last_punch": "2026-05-03T10:40:00+00:00", "total_hours": 0},
        {"id": "rec-2", "employee_id": "emp-1", "attendance_date": "2026-05-04", "first_punch": "2026-05-04T10:40:00+00:00", "last_punch": "2026-05-04T17:30:00+00:00", "total_hours": 8.0},
    ]

    with patch.object(DashboardAnalyticsService, "_fetch_records", side_effect=lambda table: profiles if table == "profiles" else records):
        result = DashboardAnalyticsService.get_employees(month=5, year=2026)

    assert len(result) == 1
    assert result[0]["total_late_count"] == 1
    assert result[0]["login_deviation"] == 1
    assert result[0]["logout_deviation"] == 1
    assert result[0]["escalations"] == 0


def test_get_employee_detail_uses_classification_flags_for_late_counts():
    profiles = [{"id": "emp-1", "full_name": "Alex Stone"}]
    records = [
        {"id": "rec-1", "employee_id": "emp-1", "attendance_date": "2026-05-03", "first_punch": "2026-05-03T14:40:00+00:00", "last_punch": "2026-05-03T21:50:00+00:00", "total_hours": 7.0},
        {"id": "rec-2", "employee_id": "emp-1", "attendance_date": "2026-05-04", "first_punch": "2026-05-04T14:40:00+00:00", "last_punch": "2026-05-04T14:40:00+00:00", "total_hours": 0},
    ]

    with patch.object(DashboardAnalyticsService, "_fetch_records", side_effect=lambda table: profiles if table == "profiles" else records):
        result = DashboardAnalyticsService.get_employee_detail("emp-1", month=5, year=2026)

    assert result["total_late_count"] == 1
    assert any(record["is_late"] for record in result["records"])
    assert any(record["is_missing_punch"] for record in result["records"])


def test_get_live_feed_keeps_attendance_date_on_each_event():
    profiles = [{"id": "emp-1", "full_name": "Priyadharshini"}]
    records = [
        {
            "id": "rec-1",
            "employee_id": "emp-1",
            "attendance_date": "2026-06-03",
            "first_punch": "2026-06-03T10:22:28+00:00",
            "last_punch": "2026-06-03T17:17:52+00:00",
            "total_hours": 8.0,
        }
    ]

    with patch.object(DashboardAnalyticsService, "_fetch_records", side_effect=lambda table: profiles if table == "profiles" else records):
        events = DashboardAnalyticsService.get_live_feed()

    assert len(events) == 1
    assert "date" in events[0]
    assert events[0]["date"] == "2026-06-03"
    assert events[0]["check_in"] == "10:22"
    assert events[0]["check_out"] == "17:17"
    assert events[0]["status"] == "EARLY_OUT"


def test_get_summary_uses_live_today_data():
    profiles = [{"id": "emp-1", "role": "EMPLOYEE", "emp_code": "EMP-1", "full_name": "Alex Stone"}]
    records = [
        {"id": "rec-1", "employee_id": "emp-1", "attendance_date": "2026-05-03", "status": "ABSENT", "first_punch": "2026-05-03T09:00:00+00:00", "last_punch": "2026-05-03T17:00:00+00:00", "total_hours": 8.0},
        {"id": "rec-2", "employee_id": "emp-1", "attendance_date": "2026-06-03", "status": "PRESENT", "first_punch": "2026-06-03T09:00:00+00:00", "last_punch": "2026-06-03T17:00:00+00:00", "total_hours": 8.0},
    ]

    with patch("app.services.dashboard_analytics_service.date") as mock_date, patch.object(DashboardAnalyticsService, "_fetch_records", side_effect=lambda table: profiles if table == "profiles" else records):
        mock_date.today.return_value = date(2026, 6, 3)
        result = DashboardAnalyticsService.get_summary()

    assert result["total_employees"] == 1
    assert result["present_today"] == 1
    assert result["absent_today"] == 0
    assert result["attendance_percentage"] == 100.0


def test_get_working_hours_uses_month_and_year_filters():
    profiles = [{"id": "emp-1", "full_name": "Alex Stone"}]
    records = [
        {"id": "rec-1", "employee_id": "emp-1", "attendance_date": "2026-05-03", "first_punch": "2026-05-03T09:00:00+00:00", "last_punch": "2026-05-03T17:00:00+00:00", "total_hours": 8.0},
        {"id": "rec-2", "employee_id": "emp-1", "attendance_date": "2026-06-03", "first_punch": "2026-06-03T09:00:00+00:00", "last_punch": "2026-06-03T17:00:00+00:00", "total_hours": 8.0},
    ]

    with patch.object(DashboardAnalyticsService, "_fetch_records", side_effect=lambda table: profiles if table == "profiles" else records):
        result = DashboardAnalyticsService.get_working_hours(month=6, year=2026)

    assert len(result) == 1
    assert result[0]["total_hours"] == 8.0


def test_get_live_feed_ignores_month_filter_and_returns_recent_activity():
    profiles = [{"id": "emp-1", "full_name": "Alex Stone"}]
    records = [
        {"id": "rec-1", "employee_id": "emp-1", "attendance_date": "2026-05-03", "first_punch": "2026-05-03T09:00:00+00:00", "last_punch": "2026-05-03T17:00:00+00:00", "total_hours": 8.0},
        {"id": "rec-2", "employee_id": "emp-1", "attendance_date": "2026-06-03", "first_punch": "2026-06-03T09:00:00+00:00", "last_punch": "2026-06-03T17:00:00+00:00", "total_hours": 8.0},
    ]

    with patch.object(DashboardAnalyticsService, "_fetch_records", side_effect=lambda table: profiles if table == "profiles" else records):
        result = DashboardAnalyticsService.get_live_feed(month=6, year=2026)

    assert len(result) == 2
    assert {event["date"] for event in result} == {"2026-06-03", "2026-05-03"}
