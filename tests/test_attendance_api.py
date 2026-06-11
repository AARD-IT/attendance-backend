from fastapi.testclient import TestClient
from app.main import app
from app.models.profile import Profile
from app import api
import pytest

client = TestClient(app)


def fake_ceo():
    return Profile(id='1111-2222-3333-4444', email='ceo@example.com', role='CEO')


def fake_employee():
    return Profile(id='2222-3333-4444-5555', email='emp@example.com', role='EMPLOYEE')


def test_ceo_can_access_attendance(monkeypatch):
    monkeypatch.setattr('app.api.attendance.require_ceo', lambda: fake_ceo())
    monkeypatch.setattr('app.services.attendance_service.attendance_service.get_all_attendance', lambda **kwargs: {"total":0, "page":1, "records": []})
    resp = client.get('/api/attendance')
    assert resp.status_code == 200


def test_employee_cannot_access_attendance(monkeypatch):
    # require_ceo raises 403
    def raise_forbidden():
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    monkeypatch.setattr('app.api.attendance.require_ceo', raise_forbidden)
    resp = client.get('/api/attendance')
    assert resp.status_code == 403


def test_employee_can_access_me(monkeypatch):
    monkeypatch.setattr('app.api.attendance.require_employee', lambda: fake_employee())
    monkeypatch.setattr('app.services.attendance_service.attendance_service.get_employee_attendance', lambda emp_id: [])
    resp = client.get('/api/attendance/me')
    assert resp.status_code == 200


def test_ceo_cannot_access_me(monkeypatch):
    def raise_forbidden():
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    monkeypatch.setattr('app.api.attendance.require_employee', raise_forbidden)
    resp = client.get('/api/attendance/me')
    assert resp.status_code == 403
