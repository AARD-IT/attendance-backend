import pytest
from unittest.mock import patch

from app.services.attendance_service import attendance_service


class DummyResp:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json


class DummyClient:
    def __init__(self, responses):
        self._responses = responses

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None, params=None):
        key = url
        return self._responses.get(key, DummyResp([], 200))


def test_get_attendance_summary(monkeypatch):
    today = "2026-06-01"

    # attendance rows for today
    attendance_rows = [
        {"employee_id": "a", "status": "PRESENT"},
        {"employee_id": "b", "status": "PRESENT"},
        {"employee_id": "c", "status": "ABSENT"},
        {"employee_id": "d", "status": "HALF_DAY"},
        {"employee_id": "e", "status": "LEAVE"},
    ]

    profiles = [
        {"id": "a", "role": "EMPLOYEE", "emp_code": "E1"},
        {"id": "b", "role": "EMPLOYEE", "emp_code": "E2"},
        {"id": "c", "role": "EMPLOYEE", "emp_code": "E3"},
        {"id": "d", "role": "EMPLOYEE", "emp_code": "E4"},
        {"id": "e", "role": "EMPLOYEE", "emp_code": "E5"},
    ]

    base = attendance_service

    def fake_client_factory(timeout=10.0):
        # first call returns attendance_rows, second returns profiles
        responses = {
            f"{base.SUPABASE_BASE}/rest/v1/attendance_daily": DummyResp(attendance_rows, 200),
            f"{base.SUPABASE_BASE}/rest/v1/attendance_records": DummyResp(attendance_rows, 200),
            f"{base.SUPABASE_BASE}/rest/v1/profiles": DummyResp(profiles, 200),
        }
        return DummyClient(responses)

    monkeypatch.setattr('httpx.Client', fake_client_factory)

    summary = attendance_service.get_attendance_summary()

    assert summary['total_employees'] == 5
    assert summary['present_today'] == 2
    assert summary['absent_today'] == 1
    assert summary['half_day_today'] == 1
    assert summary['leave_today'] == 1
