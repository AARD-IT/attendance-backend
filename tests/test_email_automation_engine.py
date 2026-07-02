from datetime import datetime as real_datetime

from app.api.ceo import send_monthly_report, send_late_login_alert
from app.services.automation_settings_service import AutomationSettingsService
from app.services.automation_email_service import AutomationEmailService
from app.services.email_reports_service import EmailReportsService
from app.services.attendance_shift_engine import AttendanceShiftEngine


class DummyResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload


def test_get_settings_returns_defaults_when_table_is_empty(monkeypatch):
    service = AutomationSettingsService()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, headers=None, params=None):
            return DummyResponse([])

    monkeypatch.setattr("app.services.automation_settings_service.httpx.Client", FakeClient)

    settings = service.get_settings()

    assert settings["monthly_report_enabled"] is False
    assert settings["monthly_report_day"] == 5
    assert settings["monthly_report_time"] == "09:00"


def test_logging_services_target_email_logs_table():
    assert "email_logs" in EmailReportsService._table_url()
    assert "email_logs" in AutomationEmailService._table_url()


def test_email_reports_log_activity_uses_resend_provider(monkeypatch):
    captured = {}

    def fake_send_email(self, recipient_email, subject, email_body, email_type, employee_name):
        captured["send_email"] = True
        return "resend-msg-123"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["json"] = json
            return DummyResponse([{"id": "1"}])

    monkeypatch.setattr("app.services.email_reports_service.httpx.Client", FakeClient)
    monkeypatch.setattr(EmailReportsService, "send_email", fake_send_email)

    service = EmailReportsService()
    service.log_activity("emp-1", "Jane", "jane@example.com", "late_login_alert", "SENT")

    assert captured["send_email"] is True
    assert captured["json"]["employee_email"] == "jane@example.com"
    assert captured["json"]["status"] == "sent"
    assert captured["json"]["provider"] == "resend"
    assert captured["json"]["provider_message_id"] == "resend-msg-123"


def test_email_reports_log_activity_records_failed_delivery(monkeypatch):
    captured = {}

    def fake_send_email(self, recipient_email, subject, email_body, email_type, employee_name):
        raise RuntimeError("Resend unavailable")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, headers=None, json=None):
            captured["json"] = json
            return DummyResponse([{"id": "1"}])

    monkeypatch.setattr("app.services.email_reports_service.httpx.Client", FakeClient)
    monkeypatch.setattr(EmailReportsService, "send_email", fake_send_email)

    service = EmailReportsService()

    try:
        service.log_activity("emp-1", "Jane", "jane@example.com", "late_login_alert", "SENT")
    except RuntimeError as exc:
        assert "Resend unavailable" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for failed delivery")

    assert captured["json"]["status"] == "failed"
    assert captured["json"]["provider"] == "resend"
    assert captured["json"]["provider_message_id"] is None


def test_build_monthly_attendance_email_uses_real_records(monkeypatch):
    monkeypatch.setattr(
        "app.services.email_reports_service.analytics_service.get_employee_detail",
        lambda employee_id, month=None, year=None: {
            "employee_name": "Jane Doe",
            "employee_code": "EMP-001",
            "records": [
                {
                    "date": "2026-06-11",
                    "weekday": "Friday",
                    "first_punch": "2026-06-11T09:45:00+05:30",
                    "last_punch": "2026-06-11T18:10:00+05:30",
                    "total_time": 8.25,
                    "status": "PRESENT",
                    "is_late": False,
                    "is_early_out": False,
                    "is_missing_punch": False,
                }
            ],
        },
    )
    monkeypatch.setattr(
        "app.services.email_reports_service.analytics_service.get_employee_monthly_attendance",
        lambda employee_id, month=None, year=None: {
            "present_days": 1,
            "login_deviation": 0,
            "logout_deviation": 0,
            "total_deviations": 0,
            "escalations": 0,
        },
    )

    html = EmailReportsService.build_monthly_attendance_email({"employee_id": "emp-1", "employee_name": "Jane Doe", "month": 6, "year": 2026})

    assert "Jane Doe" in html
    assert "EMP-001" in html
    assert "Attendance records for the selected month" in html
    assert "2026-06-11" in html


def test_build_late_login_email_uses_real_shift_data(monkeypatch):
    record = {
        "employee_id": "emp-1",
        "employee_name": "Jane Doe",
        "attendance_date": "2026-06-11",
        "first_punch": "2026-06-11T10:40:00+05:30",
        "last_punch": "2026-06-11T18:00:00+05:30",
    }

    monkeypatch.setattr(AttendanceShiftEngine, "resolve_shift_assignment", lambda record: {"shift_name": "Morning Shift", "shift_type": "Shift 1"})

    html = EmailReportsService.build_late_login_email({
        "employee_name": "Jane Doe",
        "attendance_date": "2026-06-11",
        "record": record,
        "classification": {"login_cutoff": "10:35", "logout_cutoff": "18:00"},
        "login_deviations": 1,
        "logout_deviations": 0,
        "escalations": 0,
    })

    assert "Morning Shift" in html
    assert "10:35" in html
    assert "10:40" in html


def test_build_late_login_email_prefers_assignment_shift_cutoffs(monkeypatch):
    record = {
        "employee_id": "emp-1",
        "employee_name": "Jane Doe",
        "attendance_date": "2026-06-11",
        "first_punch": "2026-06-11T15:10:00+05:30",
        "last_punch": "2026-06-11T22:10:00+05:30",
    }

    monkeypatch.setattr(AttendanceShiftEngine, "classify_record", lambda record: {"login_cutoff": "10:35", "logout_cutoff": "18:00", "shift_type": "Shift 1"})

    html = EmailReportsService.build_late_login_email({
        "employee_name": "Jane Doe",
        "attendance_date": "2026-06-11",
        "record": record,
        "assignment": {"shift_name": "Shift 2", "shift_type": "Shift 2"},
        "classification": {"login_cutoff": "10:35", "logout_cutoff": "18:00", "shift_type": "Shift 1"},
        "login_deviations": 1,
        "logout_deviations": 0,
        "escalations": 0,
    })

    assert "Shift 2" in html
    assert "Login by 14:35, Logout by 22:00" in html
    assert "15:10" in html


def test_send_monthly_report_uses_previous_completed_month(monkeypatch):
    captured = {}

    def fake_log_activity(*args, **kwargs):
        captured["context"] = kwargs["context"]
        return {"ok": True}

    monkeypatch.setattr("app.api.ceo.email_reports_service.log_activity", fake_log_activity)

    send_monthly_report({"employee_id": "emp-1", "employee_name": "Jane Doe", "recipient_email": "jane@example.com", "month": 6, "year": 2026}, current_user=None)

    assert captured["context"]["month"] == 5
    assert captured["context"]["year"] == 2026


def test_send_late_login_alert_preserves_record_context(monkeypatch):
    captured = {}

    def fake_log_activity(*args, **kwargs):
        captured["context"] = kwargs["context"]
        return {"ok": True}

    monkeypatch.setattr("app.api.ceo.email_reports_service.log_activity", fake_log_activity)

    record = {"employee_id": "emp-1", "employee_name": "Jane Doe", "attendance_date": "2026-06-11", "first_punch": "2026-06-11T10:40:00+05:30", "last_punch": "2026-06-11T18:00:00+05:30"}
    send_late_login_alert({"employee_id": "emp-1", "employee_name": "Jane Doe", "recipient_email": "jane@example.com", "attendance_date": "2026-06-11", "record": record}, current_user=None)

    assert captured["context"]["record"] == record
    assert captured["context"]["attendance_date"] == "2026-06-11"


def test_process_due_jobs_uses_previous_completed_month_for_reports(monkeypatch):
    captured = {}
    service = AutomationEmailService()

    class FakeDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 7, 4, 9, 0)

    def fake_send_monthly_reports(target_month=None):
        captured['target_month'] = target_month
        return []

    monkeypatch.setattr('app.services.automation_email_service.datetime', FakeDateTime)
    class MockResponse:
        status_code = 200
        text = "[]"
        def json(self): return []
    class MockClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs): return MockResponse()
        def post(self, *args, **kwargs): return MockResponse()
        def patch(self, *args, **kwargs): return MockResponse()
    monkeypatch.setattr('app.services.automation_settings_service.httpx.Client', MockClient)
    monkeypatch.setattr('app.services.automation_email_service.httpx.Client', MockClient)
    monkeypatch.setattr('app.services.automation_email_service.httpx.get', lambda *args, **kwargs: MockResponse())
    monkeypatch.setattr('app.services.automation_email_service.automation_settings_service.get_settings', lambda: {
        'monthly_report_enabled': True,
        'monthly_report_day': 4,
        'monthly_report_time': '09:00',
        'late_login_enabled': False,
        'late_login_delay': 'same_day',
        'late_login_time': '18:00',
        'early_logout_enabled': False,
        'early_logout_delay': 'same_day',
        'early_logout_time': '22:30',
    })
    monkeypatch.setattr(service, 'send_monthly_reports', fake_send_monthly_reports)
    monkeypatch.setattr('app.services.automation_job_log_service.automation_job_log_service.claim_job', lambda *args, **kwargs: True)
    monkeypatch.setattr('app.services.automation_job_log_service.automation_job_log_service.finalize_job', lambda *args, **kwargs: None)

    service.process_due_jobs()

    assert captured['target_month'] == '2026-06'


def test_process_due_jobs_uses_delay_for_late_login_alerts(monkeypatch):
    captured = {}
    service = AutomationEmailService()

    class FakeDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 7, 5, 18, 0)

    def fake_send_late_login_alerts(attendance_date=None):
        captured['attendance_date'] = attendance_date
        return []

    monkeypatch.setattr('app.services.automation_email_service.datetime', FakeDateTime)
    class MockResponse:
        status_code = 200
        text = "[]"
        def json(self): return []
    class MockClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs): return MockResponse()
        def post(self, *args, **kwargs): return MockResponse()
        def patch(self, *args, **kwargs): return MockResponse()
    monkeypatch.setattr('app.services.automation_settings_service.httpx.Client', MockClient)
    monkeypatch.setattr('app.services.automation_email_service.httpx.Client', MockClient)
    monkeypatch.setattr('app.services.automation_email_service.httpx.get', lambda *args, **kwargs: MockResponse())
    monkeypatch.setattr('app.services.automation_email_service.automation_settings_service.get_settings', lambda: {
        'monthly_report_enabled': False,
        'monthly_report_day': 4,
        'monthly_report_time': '09:00',
        'late_login_enabled': True,
        'late_login_delay': 'tomorrow',
        'late_login_time': '18:00',
        'early_logout_enabled': False,
        'early_logout_delay': 'same_day',
        'early_logout_time': '22:30',
    })
    monkeypatch.setattr(service, 'send_late_login_alerts', fake_send_late_login_alerts)
    monkeypatch.setattr('app.services.automation_job_log_service.automation_job_log_service.claim_job', lambda *args, **kwargs: True)
    monkeypatch.setattr('app.services.automation_job_log_service.automation_job_log_service.finalize_job', lambda *args, **kwargs: None)

    service.process_due_jobs()

    assert captured['attendance_date'] == '2026-07-04'


def test_should_send_alert_prevents_duplicate_employee_day(monkeypatch):
    service = AutomationEmailService()

    def fake_fetch_logs(*args, **kwargs):
        return [
            {
                "employee_id": "emp-1",
                "email_type": "late_login_alert",
                "status": "SENT",
                "sent_at": "2026-06-11T10:30:00",
            }
        ]

    monkeypatch.setattr(service, "_fetch_activity_logs", fake_fetch_logs)

    assert service.should_send_alert("emp-1", "2026-06-11", "late_login_alert") is False


def test_should_send_monthly_report_only_once_per_month(monkeypatch):
    service = AutomationEmailService()

    def fake_fetch_logs(*args, **kwargs):
        return [
            {
                "employee_id": "emp-1",
                "email_type": "monthly_report",
                "status": "SENT",
                "subject": "Monthly Attendance Report – June 2026",
                "sent_at": "2026-06-05T09:15:00",
            }
        ]

    monkeypatch.setattr(service, "_fetch_activity_logs", fake_fetch_logs)

    assert service.should_send_alert("emp-1", "2026-06", "monthly_report") is False


def test_send_late_login_alerts_skip_incomplete_daily_records(monkeypatch):
    service = AutomationEmailService()

    def fake_daily_attendance(*args, **kwargs):
        return {"records": [{"employee_id": "emp-1", "first_punch": None, "last_punch": None}]}

    monkeypatch.setattr("app.services.attendance_service.attendance_service.get_daily_attendance", fake_daily_attendance)
    monkeypatch.setattr("app.services.attendance_service.attendance_service.get_all_attendance", lambda *args, **kwargs: {"records": []})

    result = service.send_late_login_alerts("2026-06-11")
    assert result == []


def test_send_early_logout_alerts_skip_incomplete_daily_records(monkeypatch):
    service = AutomationEmailService()

    def fake_daily_attendance(*args, **kwargs):
        return {"records": [{"employee_id": "emp-1", "first_punch": None, "last_punch": None}]}

    monkeypatch.setattr("app.services.attendance_service.attendance_service.get_daily_attendance", fake_daily_attendance)
    monkeypatch.setattr("app.services.attendance_service.attendance_service.get_all_attendance", lambda *args, **kwargs: {"records": []})

    result = service.send_early_logout_alerts("2026-06-11")
    assert result == []
