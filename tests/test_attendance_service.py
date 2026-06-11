from unittest.mock import patch
from app.services.attendance_service import attendance_service


def test_get_attendance_summary_calculation():
    sample_rows = [
        {"employee_id": "a", "status": "PRESENT"},
        {"employee_id": "b", "status": "PRESENT"},
        {"employee_id": "c", "status": "ABSENT"},
        {"employee_id": "d", "status": "HALF_DAY"},
        {"employee_id": "e", "status": "LEAVE"},
    ]

    with patch('app.services.attendance_service.httpx.Client') as mock_client:
        # mock the attendance query
        mock_client.return_value.__enter__.return_value.get.return_value.json.return_value = sample_rows
        # mock profiles
        mock_client.return_value.__enter__.return_value.get.return_value.status_code = 200
        with patch('app.services.attendance_service.SUPABASE_BASE', 'https://test.supabase'):
            with patch('app.services.attendance_service.SUPABASE_HEADERS', {}):
                summary = attendance_service.get_attendance_summary()

    assert summary['total_employees'] >= 0
    assert summary['present_today'] == 2
    assert summary['absent_today'] == 1
    assert summary['half_day_today'] == 1
    assert summary['leave_today'] == 1
