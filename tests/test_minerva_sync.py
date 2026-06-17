"""
Tests for Minerva synchronization service.
"""

import pytest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import app.services.minerva_sync as minerva_sync_module
from app.db.supabase import SupabaseClient
from app.services.minerva_client import MinervaClient
from app.services.minerva_sync import MinervaSyncService


@pytest.fixture
def sync_service():
    """Create a MinervaSyncService instance for testing."""
    return MinervaSyncService(validate_schema=False)


@pytest.fixture
def sample_employees():
    """Sample employee data from Minerva."""
    return {
        "data": [
            {
                "emp_code": "EMP001",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@company.com",
                "mobile": "1234567890",
                "department": {"dept_name": "Engineering"},
                "position": {"position_name": "Software Engineer"}
            },
            {
                "emp_code": "EMP002",
                "first_name": "Jane",
                "last_name": "Smith",
                "email": "jane.smith@company.com",
                "mobile": "0987654321",
                "department": {"dept_name": "HR"},
                "position": {"position_name": "HR Manager"}
            }
        ]
    }


@pytest.fixture
def sample_transactions():
    """Sample attendance transaction data from Minerva."""
    return {
        "data": [
            {
                "id": "TXN001",
                "emp_code": "EMP001",
                "punch_time": "2024-01-15T09:00:00Z",
                "terminal": "Terminal1",
                "verify_type": "Face"
            },
            {
                "id": "TXN002",
                "emp_code": "EMP001",
                "punch_time": "2024-01-15T18:00:00Z",
                "terminal": "Terminal1",
                "verify_type": "Face"
            },
            {
                "id": "TXN003",
                "emp_code": "EMP002",
                "punch_time": "2024-01-15T08:30:00Z",
                "terminal": "Terminal1",
                "verify_type": "Face"
            },
            {
                "id": "TXN004",
                "emp_code": "EMP002",
                "punch_time": "2024-01-15T17:30:00Z",
                "terminal": "Terminal1",
                "verify_type": "Face"
            }
        ]
    }


class TestMinervaSyncService:
    """Tests for MinervaSyncService."""

    def test_sync_service_initialization(self, sync_service):
        """Test that sync service initializes properly."""
        assert sync_service.minerva_client is not None
        assert sync_service.supabase_url is not None
        assert sync_service.headers is not None

    def test_validate_required_columns_raises_clear_error_when_missing(self):
        """Startup validation should fail fast when required profile columns are missing."""
        with patch.object(minerva_sync_module, "MinervaClient", return_value=MagicMock()):
            with patch.object(minerva_sync_module.SupabaseClient, "get_profile_columns", return_value=["id", "email", "full_name"]):
                with pytest.raises(ValueError, match="minerva_employee_id"):
                    minerva_sync_module.MinervaSyncService()

    def test_determine_attendance_status(self, sync_service):
        """Test attendance status determination based on hours."""
        assert sync_service._determine_attendance_status(8) == "PRESENT"
        assert sync_service._determine_attendance_status(9) == "PRESENT"
        assert sync_service._determine_attendance_status(5) == "HALF_DAY"
        assert sync_service._determine_attendance_status(4) == "HALF_DAY"
        assert sync_service._determine_attendance_status(2) == "HALF_DAY"
        assert sync_service._determine_attendance_status(0) == "ABSENT"
        assert sync_service._determine_attendance_status(-1) == "ABSENT"

    def test_sync_employees_with_valid_data(self, sync_service, sample_employees):
        """Test employee sync with valid data."""
        with patch.object(sync_service.minerva_client, 'get_employees', return_value=sample_employees):
            with patch.object(sync_service, '_get_profile_by_emp_code', return_value=None):
                with patch.object(sync_service, '_insert_profile', return_value=True):
                    stats = sync_service.sync_employees()

                    assert stats["fetched"] == 2
                    assert stats["inserted"] == 2
                    assert stats["errors"] == 0

    def test_sync_employees_with_duplicates(self, sync_service, sample_employees):
        """Test that duplicate employees are updated, not inserted."""
        existing_profile = {
            "id": "user-123",
            "email": "john.doe@company.com",
            "emp_code": "EMP001"
        }

        with patch.object(sync_service.minerva_client, 'get_employees', return_value=sample_employees):
            # First employee exists, second is new
            call_count = [0]
            def get_profile_side_effect(emp_code):
                if emp_code == "EMP001":
                    return existing_profile
                return None

            with patch.object(sync_service, '_get_profile_by_emp_code', side_effect=get_profile_side_effect):
                with patch.object(sync_service, '_update_profile', return_value=True):
                    with patch.object(sync_service, '_insert_profile', return_value=True):
                        stats = sync_service.sync_employees()

                        assert stats["fetched"] == 2
                        assert stats["updated"] == 1
                        assert stats["inserted"] == 1

    def test_sync_attendance_groups_by_date(self, sync_service, sample_transactions):
        """Test that attendance transactions are properly grouped by employee and date."""
        with patch.object(sync_service.minerva_client, 'get_transactions', return_value=sample_transactions):
            profile = {"id": "user-123", "emp_code": "EMP001"}
            with patch.object(sync_service, '_get_profile_by_emp_code', return_value=profile):
                with patch.object(sync_service, '_get_attendance_record', return_value=None):
                    with patch.object(sync_service, '_insert_attendance_record', return_value=True):
                        stats = sync_service.sync_attendance()

                        assert stats["fetched"] == 4
                        # Should create 2 records (one per employee per day)
                        assert stats["inserted"] == 2

    def test_sync_all_runs_both_syncs(self, sync_service, sample_employees, sample_transactions):
        """Test that sync_all runs both employee and attendance syncs."""
        def profile_side_effect(emp_code):
            return {"id": f"user-{emp_code}"}

        with patch.object(sync_service.minerva_client, 'get_employees', return_value=sample_employees):
            with patch.object(sync_service.minerva_client, 'get_transactions', return_value=sample_transactions):
                with patch.object(sync_service, '_get_profile_by_emp_code', side_effect=profile_side_effect):
                    with patch.object(sync_service, '_update_profile', return_value=True):
                        with patch.object(sync_service, '_insert_profile', return_value=True):
                            with patch.object(sync_service, '_get_attendance_record', return_value=None):
                                with patch.object(sync_service, '_insert_attendance_record', return_value=True):
                                    stats = sync_service.sync_all()

                                assert stats["success"] is True
                                assert stats["employees_synced"] > 0
                                assert stats["attendance_synced"] > 0
                                assert stats["attendance_skipped"] == 0
                                assert "total_execution_time_seconds" in stats

    def test_sync_all_skips_when_previous_run_is_active(self, sync_service):
        """Test that overlapping sync runs are skipped when a run is already active."""
        active_state = {
            "status": "RUNNING",
            "updated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        }

        with patch.object(sync_service, 'get_last_sync_state', return_value=active_state):
            with patch.object(sync_service, 'sync_employees') as sync_employees:
                with patch.object(sync_service, 'sync_attendance') as sync_attendance:
                    stats = sync_service.sync_all()

        assert stats["skipped"] is True
        assert stats["reason"] == "sync_in_progress"
        sync_employees.assert_not_called()
        sync_attendance.assert_not_called()

    def test_sync_attendance_skips_unmapped_employee(self, sync_service):
        """Test that attendance sync skips records when no employee profile exists."""
        transactions = {
            "data": [
                {
                    "id": "TXN001",
                    "emp_code": "UNKNOWN",
                    "punch_time": "2026-04-08 11:27:17",
                    "terminal": "Terminal1",
                    "verify_type": "Face",
                }
            ]
        }

        with patch.object(sync_service.minerva_client, 'get_transactions', return_value=transactions):
            with patch.object(sync_service, '_get_profile_by_emp_code', return_value=None):
                stats = sync_service.sync_attendance()

                assert stats["fetched"] == 1
                assert stats["inserted"] == 0
                assert stats["updated"] == 0
                assert stats["skipped"] == 1
                assert stats["errors"] == 0

    def test_sync_attendance_records_failed_state_on_invalid_transactions(self, sync_service):
        """Test that invalid transaction payloads persist a failed sync state."""
        with patch.object(sync_service.minerva_client, 'get_transactions', return_value={"data": {}}):
            with patch.object(sync_service, 'save_sync_state', return_value={"success": False}):
                stats = sync_service.sync_attendance()

                assert stats["errors"] == 1
                assert stats["inserted"] == 0
                assert stats["updated"] == 0
                sync_service.save_sync_state.assert_called_once_with(records_synced=0, status="FAILED")

    def test_sync_handles_missing_data_gracefully(self, sync_service):
        """Test that sync handles missing required fields gracefully."""
        employees_with_missing_fields = {
            "data": [
                {"first_name": "John"},  # Missing emp_code and email
                {"emp_code": "EMP001"}  # Missing first_name and email
            ]
        }

        with patch.object(sync_service.minerva_client, 'get_employees', return_value=employees_with_missing_fields):
            stats = sync_service.sync_employees()

            assert stats["fetched"] == 2
            assert stats["skipped"] == 2
            assert stats["inserted"] == 0

    def test_sync_employee_import_uses_minerva_id_and_placeholder_email(self, sync_service):
        """Test that Minerva employees are imported even when email is missing and Minerva IDs are stored."""
        employees = {
            "data": [
                {
                    "id": 15,
                    "emp_code": "EMP015",
                    "first_name": "Rafiq",
                    "last_name": "Khan",
                    "department": {"dept_name": "Operations"},
                    "position": {"position_name": "Executive"},
                }
            ]
        }

        with patch.object(sync_service.minerva_client, 'get_employees', return_value=employees):
            with patch.object(sync_service, '_get_profile_by_emp_code', return_value=None):
                with patch.object(sync_service, '_update_profile', return_value=True) as update_profile:
                    with patch.object(sync_service, '_insert_profile', return_value={"id": "profile-15"}) as insert_profile:
                        stats = sync_service.sync_employees()

        assert stats["inserted"] == 1
        assert stats["errors"] == 0
        assert insert_profile.call_args.kwargs["email"] == "rafiq.khan@minerva.local"
        assert update_profile.call_args.kwargs["minerva_employee_id"] == "15"

    def test_parse_punch_time_accepts_common_minerva_formats(self, sync_service):
        """Test that common Minerva punch_time formats parse successfully."""
        samples = [
            "2026-04-08 11:27:17",
            "2026-04-07T18:22:19",
            "2026-04-07T18:22:19Z",
            "2026-04-07T18:22:19+00:00",
        ]

        parsed = [sync_service._parse_punch_time(value) for value in samples]

        assert all(item is not None for item in parsed)
        assert all(item.tzinfo is not None for item in parsed)

    def test_sync_attendance_does_not_skip_valid_naive_punch_times(self, sync_service):
        """Test that attendance sync accepts valid punch_time values without T/Z markers."""
        transactions = {
            "data": [
                {
                    "id": "TXN001",
                    "emp_code": "EMP001",
                    "punch_time": "2026-04-08 11:27:17",
                    "terminal": "Terminal1",
                    "verify_type": "Face",
                }
            ]
        }

        with patch.object(sync_service.minerva_client, 'get_transactions', return_value=transactions):
            with patch.object(sync_service, '_get_profile_by_emp_code', return_value={"id": "user-123"}):
                with patch.object(sync_service, '_get_attendance_record', return_value=None):
                    with patch.object(sync_service, '_insert_attendance_record', return_value={"success": True}):
                        stats = sync_service.sync_attendance()

                        assert stats["fetched"] == 1
                        assert stats["inserted"] == 1
                        assert stats["skipped"] == 0
                        assert stats["errors"] == 0

    def test_build_sync_window_uses_last_7_days_if_no_last_sync(self, sync_service):
        """Sync should default to the past 7 days when no last sync exists."""
        start_date, end_date = sync_service._build_sync_window(date(2026, 6, 9))

        assert start_date == "2026-06-02"
        assert end_date == "2026-06-09"

    def test_build_sync_window_wraps_year_boundary_using_last_7_days(self, sync_service):
        """The window should use the previous 7 days across year boundaries."""
        start_date, end_date = sync_service._build_sync_window(date(2027, 1, 10))

        assert start_date == "2027-01-03"
        assert end_date == "2027-01-10"

    def test_build_sync_window_uses_last_sync_timestamp_for_incremental_sync(self, sync_service):
        """Incremental sync should use the stored last sync timestamp instead of a full historical window."""
        last_sync = datetime(2026, 6, 10, 12, 30, 0)

        start_date, end_date = sync_service._build_sync_window(date(2026, 6, 15), last_sync_timestamp=last_sync)

        assert start_date == "2026-06-10T12:30:00"
        assert end_date == "2026-06-15"

    def test_get_transactions_uses_date_filters(self):
        """Minerva transaction fetching should pass start_date/end_date to the API."""
        client = MinervaClient()

        with patch("app.services.minerva_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {"data": []}
            mock_get.return_value = mock_response

            client.get_transactions(start_date="2026-05-01", end_date="2026-06-10")

        assert mock_get.call_args.kwargs["params"] == {"start_date": "2026-05-01", "end_date": "2026-06-10"}

    def test_build_sync_window_uses_last_7_days_if_no_last_sync(self, sync_service):
        """Sync should default to the past 7 days when no last sync exists."""
        start_date, end_date = sync_service._build_sync_window(date(2026, 6, 15))

        assert start_date == "2026-06-08"
        assert end_date == "2026-06-15"

    def test_fetch_paginated_retries_and_skips_failed_page(self):
        """Minerva pagination should retry transient page failures and return collected records."""
        client = MinervaClient()

        first_response = MagicMock(status_code=200)
        first_response.json.return_value = {"data": [{"id": "TXN001"}], "next": "https://api.next/page/2"}
        second_response = MagicMock(status_code=502)
        third_response = MagicMock(status_code=502)
        fourth_response = MagicMock(status_code=502)
        fifth_response = MagicMock(status_code=502)

        with patch("app.services.minerva_client.requests.get", side_effect=[first_response, second_response, third_response, fourth_response, fifth_response]) as mock_get:
            result = client.get_transactions(start_date="2026-06-08", end_date="2026-06-15")

        assert result == [{"id": "TXN001"}]
        assert client.partial_fetch is True
        assert mock_get.call_count == 5
        assert mock_get.call_args_list[0].kwargs["params"] == {"start_date": "2026-06-08", "end_date": "2026-06-15"}

    def test_sync_attendance_returns_partial_success_if_some_pages_fail(self, sync_service):
        """Attendance sync should return partial success when some pages failed after collecting records."""
        transactions = [
            {
                "id": "TXN001",
                "emp_code": "EMP001",
                "punch_time": "2026-06-10T09:00:00Z",
                "terminal": "Terminal1",
                "verify_type": "Face",
            }
        ]

        with patch.object(sync_service.minerva_client, 'get_transactions', return_value=transactions):
            with patch.object(sync_service, '_get_profile_by_emp_code', return_value={"id": "user-123"}):
                with patch.object(sync_service, '_get_attendance_record', return_value=None):
                    with patch.object(sync_service, '_insert_attendance_record', return_value={"success": True}):
                        with patch.object(sync_service, 'save_sync_state', return_value={"success": True}) as save_state:
                            sync_service.minerva_client.partial_fetch = True
                            stats = sync_service.sync_attendance()

        assert stats["success"] is True
        assert stats["partial_sync"] is True
        save_state.assert_called_once_with(records_synced=1, status="FAILED")

    def test_upsert_sync_state_does_not_update_last_sync_at_on_failed(self):
        """Supabase sync state upsert should not set last_sync_at for failed syncs."""
        fake_client = MagicMock()
        fake_response = MagicMock(status_code=200)
        fake_response.json.return_value = [{"id": "global", "status": "FAILED"}]
        fake_client.__enter__.return_value.post.return_value = fake_response

        with patch("app.db.supabase.httpx.Client", return_value=fake_client):
            SupabaseClient.upsert_sync_state(records_synced=0, status="FAILED")

        sent_payload = fake_client.__enter__.return_value.post.call_args.kwargs["json"]
        assert sent_payload["id"] == "global"
        assert sent_payload["records_synced"] == 0
        assert sent_payload["status"] == "FAILED"
        assert "last_sync_at" not in sent_payload
        assert "updated_at" in sent_payload

    def test_compute_day_punch_bounds_uses_true_min_and_max(self, sync_service):
        """Test that day-level bounds come from min/max punch_time, not list position."""
        transactions = [
            {"punch_time": "2024-01-15T16:00:00+00:00"},
            {"punch_time": "2024-01-15T10:19:00+00:00"},
            {"punch_time": "2024-01-15T21:30:00+00:00"},
        ]

        first_punch, last_punch = sync_service._compute_day_punch_bounds(transactions)

        expected_first = datetime.fromisoformat("2024-01-15T10:19:00+00:00").astimezone()
        expected_last = datetime.fromisoformat("2024-01-15T21:30:00+00:00").astimezone()

        assert first_punch == expected_first
        assert last_punch == expected_last

    def test_sync_handles_api_errors(self, sync_service):
        """Test that sync handles Minerva API errors gracefully."""
        from requests.exceptions import RequestException

        with patch.object(sync_service.minerva_client, 'get_employees', side_effect=RequestException("API Error")):
            stats = sync_service.sync_employees()

            assert stats["errors"] > 0
            assert "error_details" in stats

    def test_upsert_attendance_record_uses_conflict_target(self):
        """Ensure attendance upserts target the unique employee/date key for real updates."""
        fake_client = MagicMock()
        fake_response = MagicMock()
        fake_response.status_code = 201
        fake_response.json.return_value = [{"id": "record-1"}]
        fake_client.__enter__.return_value.post.return_value = fake_response

        with patch("app.db.supabase.httpx.Client", return_value=fake_client):
            with patch("app.db.supabase.settings.SUPABASE_URL", "https://example.supabase.co"):
                result = SupabaseClient.upsert_attendance_record(
                    employee_id="emp-1",
                    attendance_date="2026-04-22",
                    first_punch="2026-04-22T10:19:04+00:00",
                    last_punch="2026-04-22T16:00:51+00:00",
                    total_hours=5.7,
                    status="PRESENT",
                )

        assert result["success"] is True
        fake_client.__enter__.return_value.post.assert_called_once()
        _, kwargs = fake_client.__enter__.return_value.post.call_args
        assert kwargs["params"] == {"on_conflict": "employee_id,attendance_date"}
        assert kwargs["headers"]["Prefer"] == "resolution=merge-duplicates,return=representation"
