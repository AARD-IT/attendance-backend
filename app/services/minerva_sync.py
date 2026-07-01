"""
Minerva data synchronization service.
Handles syncing employee and attendance data from Minerva to Supabase.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import date, datetime, timezone, timedelta

from fastapi import HTTPException
from app.core.config import settings
from app.services.attendance_shift_engine import AttendanceShiftEngine
from app.services.minerva_client import MinervaClient
from app.db.supabase import SupabaseClient
import uuid

logger = logging.getLogger(__name__)


class MinervaSyncService:
    """Service for synchronizing Minerva data to Supabase."""

    @staticmethod
    def _parse_punch_time(value):
        """Parse a Minerva punch_time value into datetime."""
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed

        except Exception as e:
            logger.warning(f"Failed to parse punch time {value}: {e}")
            return None

    @staticmethod
    def _compute_day_punch_bounds(day_transactions: List[Dict[str, Any]]) -> Tuple[datetime, datetime]:
        """Compute the true first and last punch for a day using min/max values."""
        parsed_times = [MinervaSyncService._parse_punch_time(item.get('punch_time')) for item in day_transactions]
        parsed_times = [value for value in parsed_times if value is not None]

        if not parsed_times:
            raise ValueError("No valid punch times found for attendance day")

        return min(parsed_times), max(parsed_times)

    def __init__(self, validate_schema: bool = True):
        """Initialize the sync service with Minerva client."""
        if validate_schema:
            self._validate_required_columns()
        self.minerva_client = MinervaClient()
        self.supabase_url = settings.SUPABASE_URL
        self.headers = {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        }

    @staticmethod
    def _validate_required_columns(required_columns: Optional[List[str]] = None) -> None:
        """Fail fast when the production profiles schema is missing required columns for Minerva sync."""
        required_columns = required_columns or ["emp_code", "minerva_employee_id"]
        available_columns = set(SupabaseClient.get_profile_columns())

        missing = [column for column in required_columns if column not in available_columns]
        if missing:
            raise ValueError(
                "Profiles schema is missing required Minerva sync columns: "
                + ", ".join(missing)
                + ". Apply the pending migration before running synchronization."
            )

    @staticmethod
    def _normalize_text(value: Any) -> Optional[str]:
        """Normalize raw Minerva text values to usable strings."""
        if value is None:
            return None
        if isinstance(value, dict):
            for key in ("dept_name", "department_name", "name", "position_name", "title"):
                nested = value.get(key)
                if nested:
                    return str(nested).strip()
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _minerva_employee_id(employee: Dict[str, Any]) -> Optional[str]:
        """Extract the real Minerva employee identifier for reporting and display."""
        for key in ("id", "employee_id", "emp_id", "minerva_employee_id"):
            value = employee.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return None

    @staticmethod
    def _fallback_email(first_name: str, last_name: str, emp_code: str) -> str:
        """Generate a stable placeholder email for Minerva employees without an email address."""
        base_name = "employee"
        if first_name or last_name:
            base_name = f"{(first_name or '').strip()}.{(last_name or '').strip()}".replace(' ', '.').lower().strip('.')
        if not base_name:
            base_name = str(emp_code).lower().replace(' ', '-')
        return f"{base_name or 'employee'}@minerva.local"

    def _get_profile_by_emp_code(self, emp_code: str):
        """Compatibility wrapper for fetching a profile by employee code."""
        return SupabaseClient.fetch_profile_by_emp_code(emp_code)

    def _insert_profile(self, *args, **kwargs):
        """Compatibility wrapper for creating a profile."""
        return SupabaseClient.create_profile(*args, **kwargs)

    def _update_profile(self, *args, **kwargs):
        """Compatibility wrapper for updating a profile."""
        return SupabaseClient.update_profile(*args, **kwargs)

    def _get_attendance_record(self, employee_id: str, attendance_date: str):
        """Compatibility wrapper for fetching an attendance record."""
        return SupabaseClient.fetch_attendance_record(employee_id, attendance_date)

    def _insert_attendance_record(self, *args, **kwargs):
        """Compatibility wrapper for upserting an attendance record."""
        return SupabaseClient.upsert_attendance_record(*args, **kwargs)

    def _store_raw_log(self, *args, **kwargs):
        """Compatibility wrapper for storing raw Minerva punches."""
        return SupabaseClient.upsert_minerva_raw_log(*args, **kwargs)

    def _store_daily_attendance(self, *args, **kwargs):
        """Compatibility wrapper for storing normalized daily attendance."""
        return SupabaseClient.upsert_daily_attendance_record(*args, **kwargs)

    @staticmethod
    def _build_sync_window(reference_date: Optional[date] = None, last_sync_timestamp: Optional[datetime] = None) -> Tuple[str, str]:
        """Return the sync window used for Minerva fetches.

        When a last sync timestamp is available, fetch only the delta since that time.
        Otherwise use the previous month through today to avoid a full historical reload.
        """
        today = reference_date or date.today()

        if last_sync_timestamp is not None:
            if last_sync_timestamp.tzinfo is None:
                normalized = last_sync_timestamp.replace(tzinfo=timezone.utc)
            else:
                normalized = last_sync_timestamp.astimezone(timezone.utc)
            normalized = normalized.replace(microsecond=0)
            return normalized.isoformat(timespec="seconds").replace('+00:00', ''), today.isoformat()

        start_date = today - timedelta(days=7)
        end_date = today
        return start_date.isoformat(), end_date.isoformat()

        previous_month = current_month - 1
        previous_month_year = current_year
        if previous_month == 0:
            previous_month = 12
            previous_month_year -= 1

        start_date = date(previous_month_year, previous_month, 1)
        end_date = today

        return start_date.isoformat(), end_date.isoformat()

    def sync_employees(self) -> Dict[str, Any]:
        """
        Sync employee data from Minerva to Supabase profiles.
        
        Updates existing profiles with emp_code and employee info from Minerva.
        Only profiles that already exist (have corresponding auth users) are updated.
        
        Returns:
            Dict with sync statistics (inserted, updated, skipped, errors)
        """
        logger.info("Starting employee sync from Minerva")
        start_time = datetime.utcnow()
        
        stats = {
            "fetched": 0,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "error_details": []
        }

        try:
            # Fetch employees from Minerva
            minerva_data = self.minerva_client.get_employees()
            employees = minerva_data.get('data', []) if isinstance(minerva_data, dict) else minerva_data
            
            if not isinstance(employees, list):
                logger.error(f"Invalid employees data format from Minerva: {type(employees)}")
                stats["errors"] += 1
                stats["error_details"].append("Invalid employees data format from Minerva")
                return stats

            stats["fetched"] = len(employees)
            logger.info(f"Fetched {len(employees)} employees from Minerva")

            for employee in employees:
                try:
                    # Extract employee data from Minerva response
                    emp_code = str(employee.get('emp_code') or employee.get('employee_code') or '').strip()
                    first_name = str(employee.get('first_name') or '').strip() or self._normalize_text(employee.get('name')) or ''
                    last_name = str(employee.get('last_name') or '').strip()
                    email = str(employee.get('email') or '').strip() or self._fallback_email(first_name, last_name, emp_code)
                    minerva_employee_id = self._minerva_employee_id(employee) or emp_code
                    department = self._normalize_text(employee.get('department')) or self._normalize_text(employee.get('dept'))
                    position = self._normalize_text(employee.get('position'))
                    mobile = str(employee.get('mobile') or '').strip() or None

                    # Validate critical fields
                    if not emp_code or not first_name:
                        logger.warning(f"Skipping employee with incomplete data: {employee}")
                        stats["skipped"] += 1
                        continue

                    full_name = f"{first_name} {last_name}".strip() or email.split('@')[0]

                    # Try to find existing profile by emp_code first, then by email.
                    try:
                        existing = self._get_profile_by_emp_code(emp_code)
                        if not existing:
                            existing = SupabaseClient.fetch_profile_by_email(email)
                    except HTTPException as http_exc:
                        detail = http_exc.detail if isinstance(http_exc.detail, dict) else {"error": str(http_exc.detail)}
                        supabase_response = detail.get('response', 'No response')
                        status_code = detail.get('status_code', 'Unknown')
                        logger.error(
                            f"Failed to fetch profile by email for emp_code={emp_code}: "
                            f"status={status_code}, response={supabase_response}"
                        )
                        stats["errors"] += 1
                        stats["error_details"].append(f"Query failed for emp_code={emp_code}: {supabase_response}")
                        continue
                    except Exception as e:
                        logger.error(f"Failed to query profile for emp_code={emp_code} email={email}: {str(e)}")
                        stats["errors"] += 1
                        stats["error_details"].append(f"Query failed for emp_code={emp_code}")
                        continue

                    if existing:
                        # Update existing profile with emp_code
                        try:
                            self._update_profile(
                                existing['id'],
                                full_name=full_name,
                                emp_code=emp_code,
                                minerva_employee_id=minerva_employee_id,
                                first_name=first_name,
                                last_name=last_name,
                                mobile=mobile,
                                department=department,
                                position=position,
                            )
                            stats["updated"] += 1
                            logger.info(f"Employee updated emp_code={emp_code} email={email} id={existing.get('id')}")
                        except Exception as e:
                            logger.error(f"Failed to update profile for emp_code={emp_code}: {str(e)}")
                            stats["errors"] += 1
                            stats["error_details"].append(f"Failed to update profile for emp_code={emp_code}")
                    else:
                        # Profile doesn't exist - create one
                        try:
                            # Generate a UUID for the new profile id (no auth user created)
                            new_id = str(uuid.uuid4())
                            created_profile = self._insert_profile(
                                user_id=new_id,
                                email=email,
                                role='EMPLOYEE',
                                full_name=full_name or email.split('@')[0]
                            )

                            # Add additional Minerva fields to the profile
                            try:
                                self._update_profile(
                                    created_profile.get('id', new_id) if isinstance(created_profile, dict) else new_id,
                                    emp_code=emp_code,
                                    minerva_employee_id=minerva_employee_id,
                                    first_name=first_name,
                                    last_name=last_name,
                                    mobile=mobile,
                                    department=department,
                                    position=position,
                                )
                            except Exception:
                                # Non-fatal: we still consider profile created even if extra fields fail
                                logger.warning(f"Profile created but failed to set extra fields for emp_code={emp_code} email={email}")

                            stats["inserted"] += 1
                            created_profile_id = created_profile.get('id', new_id) if isinstance(created_profile, dict) else new_id
                            logger.info(f"Employee inserted emp_code={emp_code} email={email} id={created_profile_id}")

                        except HTTPException as http_exc:
                            # Extract Supabase error details from HTTPException
                            detail = http_exc.detail if isinstance(http_exc.detail, dict) else {"error": str(http_exc.detail)}
                            supabase_response = detail.get('response', 'No response')
                            status_code = detail.get('status_code', 'Unknown')
                            logger.error(
                                f"Supabase profile creation failed for emp_code={emp_code} email={email}: "
                                f"status={status_code}, response={supabase_response}",
                                exc_info=True
                            )
                            stats["errors"] += 1
                            error_msg = f"Supabase error (status {status_code}): {supabase_response}"
                            stats["error_details"].append(error_msg)
                        except Exception as e:
                            logger.error(f"Failed to create profile for emp_code={emp_code} email={email}: {str(e)}", exc_info=e)
                            stats["errors"] += 1
                            stats["error_details"].append(f"Failed to create profile for emp_code={emp_code}: {str(e)}")

                except Exception as e:
                    logger.error(f"Error syncing employee: {str(e)}", exc_info=e)
                    stats["errors"] += 1
                    stats["error_details"].append(f"Employee sync error: {str(e)}")

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            stats["execution_time_seconds"] = execution_time
            logger.info(f"Employee sync completed in {execution_time:.2f}s - Stats: {stats}")

        except Exception as e:
            logger.error(f"Employee sync failed: {str(e)}", exc_info=e)
            stats["errors"] += 1
            stats["error_details"].append(f"Employee sync failed: {str(e)}")

        return stats

    def debug_attendance(self, emp_code: str, attendance_date: str) -> Dict[str, Any]:
        """Return a debug view for a single employee/date attendance group."""
        transactions = self.minerva_client.get_transactions()
        if not isinstance(transactions, list):
            raise ValueError("Invalid transaction payload from Minerva client")

        day_transactions = []
        for transaction in transactions:
            try:
                tx_emp_code = str(transaction.get('emp_code', '')).strip()
                punch_time = self._parse_punch_time(transaction.get('punch_time'))
                if tx_emp_code != emp_code or not punch_time:
                    continue
                if punch_time.date().isoformat() != attendance_date:
                    continue
                day_transactions.append({
                    'transaction': transaction,
                    'punch_time': punch_time,
                    'attendance_date': attendance_date,
                    'punch_time_text': transaction.get('punch_time')
                })
            except Exception:
                continue

        if not day_transactions:
            raise HTTPException(status_code=404, detail="No transactions found for that employee/date")

        sorted_transactions = sorted(day_transactions, key=lambda item: item['punch_time'])
        first_punch = sorted_transactions[0]['punch_time']
        last_punch = sorted_transactions[-1]['punch_time']
        total_hours = max(0.0, (last_punch - first_punch).total_seconds() / 3600)

        return {
            "emp_code": emp_code,
            "attendance_date": attendance_date,
            "transaction_count": len(sorted_transactions),
            "transactions": [
                {
                    "id": transaction.get('id'),
                    "emp_code": transaction.get('emp_code'),
                    "punch_time": transaction.get('punch_time'),
                    "upload_time": transaction.get('upload_time'),
                    "terminal": transaction.get('terminal'),
                    "verify_type": transaction.get('verify_type')
                }
                for transaction in [item['transaction'] for item in sorted_transactions]
            ],
            "first_punch": first_punch.astimezone().isoformat(),
            "last_punch": last_punch.astimezone().isoformat(),
            "total_hours": round(total_hours, 2),
        }

    def get_last_sync_state(self) -> Optional[Dict[str, Any]]:
        """Read the last Minerva sync marker from Supabase, if present."""
        try:
            return SupabaseClient.fetch_last_sync_state()
        except Exception as exc:
            logger.warning("Unable to fetch Minerva sync state: %s", exc)
            return None

    def save_sync_state(self, records_synced: int, status: str = "OK") -> Dict[str, Any]:
        """Persist the last successful sync metadata for incremental fetches."""
        try:
            return SupabaseClient.upsert_sync_state(records_synced=records_synced, status=status)
        except Exception as exc:
            logger.warning("Unable to persist Minerva sync state: %s", exc)
            return {"success": False, "error": str(exc)}

    @staticmethod
    def _sync_state_is_active(sync_state: Optional[Dict[str, Any]], max_age_minutes: int = 45) -> bool:
        if not sync_state:
            return False

        status = str(sync_state.get("status") or "").upper()
        if status not in {"RUNNING", "LOCKED"}:
            return False

        updated_at = sync_state.get("updated_at") or sync_state.get("last_sync_at")
        if not updated_at:
            return False

        try:
            parsed = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        except ValueError:
            return False

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
        return age <= timedelta(minutes=max_age_minutes)

    def sync_attendance(self, last_sync_timestamp: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Sync attendance data from Minerva to Supabase attendance_records.
        
        Returns:
            Dict with sync statistics (inserted, updated, skipped, errors)
        """
        logger.info("===== ATTENDANCE SYNC START =====")
        start_time = datetime.utcnow()
        
        stats = {
            "success": True,
            "partial_sync": False,
            "fetched": 0,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "error_details": []
        }

        try:
            start_date, end_date = self._build_sync_window(last_sync_timestamp=last_sync_timestamp)
            logger.info("Incremental sync window start=%s end=%s", start_date, end_date)
            
            logger.info("BEFORE CALL self.minerva_client.get_transactions")
            transactions = self.minerva_client.get_transactions(
                start_date=start_date,
                end_date=end_date
            )
            logger.info("AFTER CALL self.minerva_client.get_transactions")
            if isinstance(transactions, dict):
                transactions = transactions.get("data") if "data" in transactions else transactions
            
            if not isinstance(transactions, list):
                logger.error(f"Invalid transactions data format from Minerva: {type(transactions)}")
                stats["errors"] += 1
                stats["success"] = False
                stats["error_details"].append("Invalid transactions data format from Minerva")
                self.save_sync_state(records_synced=0, status="FAILED")
                return stats

            stats["partial_sync"] = getattr(self.minerva_client, "partial_fetch", False)
            if stats["partial_sync"] and len(transactions) > 0:
                stats["success"] = True
                stats["error_details"].append("Partial attendance sync due to skipped Minerva pages")

            stats["fetched"] = len(transactions)
            logger.info(f"Fetched {len(transactions)} transactions from Minerva")

            # Group transactions by emp_code and date for efficient processing
            transactions_by_employee_date: Dict[Tuple[str, str], List[Dict]] = {}
            
            for index, transaction in enumerate(transactions, start=1):
                try:
                    emp_code = str(transaction.get('emp_code', '')).strip()
                    punch_time_str = transaction.get('punch_time', '')
                    
                    if not emp_code or not punch_time_str:
                        stats["skipped"] += 1
                        continue

                    try:
                        punch_time = self._parse_punch_time(punch_time_str)
                        if punch_time is None:
                            raise ValueError("Invalid punch time")
                        attendance_date = punch_time.date().isoformat()
                    except (ValueError, AttributeError):
                        stats["skipped"] += 1
                        continue

                    key = (emp_code, attendance_date)
                    if key not in transactions_by_employee_date:
                        transactions_by_employee_date[key] = []
                    transactions_by_employee_date[key].append({
                        'transaction': transaction,
                        'punch_time': punch_time,
                        'attendance_date': attendance_date
                    })

                except Exception as e:
                    stats["skipped"] += 1

            logger.info("GROUPING COMPLETE groups=%s", len(transactions_by_employee_date))

            raw_logs_payloads = []
            daily_attendance_payloads = []
            attendance_records_payloads = []

            # Process grouped transactions
            for index, ((emp_code, attendance_date), day_transactions) in enumerate(transactions_by_employee_date.items(), start=1):
                try:
                    sorted_transactions = sorted(day_transactions, key=lambda item: item['punch_time'])
                    
                    # Get employee profile by emp_code
                    profile = self._get_profile_by_emp_code(emp_code)
                    if not profile:
                        stats["skipped"] += len(day_transactions)
                        continue

                    employee_id = profile["id"]
                    employee_name = str(profile.get("full_name") or f"{profile.get('first_name') or ''} {profile.get('last_name') or ''}".strip() or emp_code)

                    # Compute first and last punch strictly from sorted punch_time values.
                    first_punch = sorted_transactions[0]['punch_time']
                    last_punch = sorted_transactions[-1]['punch_time']

                    # Calculate total hours from the true first/last punch window.
                    hours_diff = (last_punch - first_punch).total_seconds() / 3600
                    total_hours = max(0.0, hours_diff)

                    # Determine status
                    status = self._determine_attendance_status(total_hours)
                    classification = AttendanceShiftEngine.classify_record({
                        "employee_id": employee_id,
                        "employee_name": employee_name,
                        "attendance_date": attendance_date,
                        "first_punch": first_punch.astimezone().isoformat(),
                        "last_punch": last_punch.astimezone().isoformat(),
                        "total_hours": total_hours,
                    })

                    # Use the earliest transaction ID as reference metadata only.
                    minerva_transaction_id = str(sorted_transactions[0]['transaction'].get('id', '')).strip()

                    # 1. Raw logs payload
                    for item in sorted_transactions:
                        raw_logs_payloads.append({
                            "employee_code": emp_code,
                            "employee_id": employee_id,
                            "timestamp": item['transaction'].get("punch_time"),
                            "raw_payload": item['transaction']
                        })

                    # 2. Daily attendance payload
                    daily_attendance_payloads.append({
                        "employee_id": employee_id,
                        "employee_name": employee_name,
                        "attendance_date": attendance_date,
                        "first_in": first_punch.astimezone().isoformat(),
                        "last_out": last_punch.astimezone().isoformat(),
                        "first_punch": first_punch.astimezone().isoformat(),
                        "last_punch": last_punch.astimezone().isoformat(),
                        "working_hours": total_hours,
                        "attendance_status": status,
                        "shift": classification.get("shift_type") or "Shift 1",
                        "late_login_flag": bool(classification.get("is_late")),
                        "early_logout_flag": bool(classification.get("is_early_out")),
                    })

                    # 3. Attendance records payload
                    attendance_records_payloads.append({
                        "employee_id": employee_id,
                        "attendance_date": attendance_date,
                        "first_punch": first_punch.astimezone().isoformat(),
                        "last_punch": last_punch.astimezone().isoformat(),
                        "total_hours": total_hours,
                        "status": status,
                        "minerva_transaction_id": minerva_transaction_id if minerva_transaction_id else None
                    })

                    stats["inserted"] += 1  # Standard counts for display

                except Exception as e:
                    stats["errors"] += 1
                    stats["error_details"].append(f"Error processing day transactions for {emp_code}/{attendance_date}: {str(e)}")

            logger.info("ATTENDANCE RECORDS BUILT count=%s", len(transactions_by_employee_date))
            
            # Batch operations
            if raw_logs_payloads:
                logger.info("Batch upserting raw logs: count=%d", len(raw_logs_payloads))
                SupabaseClient.upsert_minerva_raw_logs_batch(raw_logs_payloads)
                
            if daily_attendance_payloads:
                logger.info("Batch upserting daily attendance: count=%d", len(daily_attendance_payloads))
                SupabaseClient.upsert_daily_attendance_records_batch(daily_attendance_payloads)
                
            if attendance_records_payloads:
                logger.info("Batch upserting attendance records: count=%d", len(attendance_records_payloads))
                SupabaseClient.upsert_attendance_records_batch(attendance_records_payloads)

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            stats["execution_time_seconds"] = execution_time
            stats["success"] = stats.get("errors", 0) == 0

            self.save_sync_state(
                records_synced=stats.get("inserted", 0) + stats.get("updated", 0),
                status="SUCCESS" if stats.get("errors", 0) == 0 and not stats["partial_sync"] else "FAILED"
            )

        except Exception as e:
            logger.error(f"Attendance sync failed: {str(e)}", exc_info=e)
            stats["errors"] += 1
            stats["success"] = False
            stats["error_details"].append(f"Attendance sync failed: {str(e)}")
            self.save_sync_state(records_synced=0, status="FAILED")

        return stats

    def sync_all(self) -> Dict[str, Any]:
        """
        Run complete sync synchronously: employees first, then attendance.
        (Retained for backward compatibility and tests).
        """
        logger.info("Starting complete Minerva sync (sync)")
        start_time = datetime.utcnow()

        active_state = self.get_last_sync_state()
        if self._sync_state_is_active(active_state):
            logger.info("Skipping sync_all because a previous run is still active: %s", active_state)
            return {
                "success": True,
                "skipped": True,
                "reason": "sync_in_progress",
                "employees_synced": 0,
                "employees_inserted": 0,
                "employees_updated": 0,
                "employees_skipped": 0,
                "employees_errors": 0,
                "attendance_synced": 0,
                "attendance_inserted": 0,
                "attendance_updated": 0,
                "attendance_skipped": 0,
                "attendance_errors": 0,
                "total_execution_time_seconds": 0,
                "employee_stats": {},
                "attendance_stats": {},
            }

        self.save_sync_state(records_synced=0, status="RUNNING")

        employee_stats = self.sync_employees()
        attendance_stats = self.sync_attendance()

        execution_time = (datetime.utcnow() - start_time).total_seconds()

        # Update sync state to SUCCESS or FAILED
        is_success = employee_stats["errors"] == 0 and attendance_stats["errors"] == 0
        self.save_sync_state(
            records_synced=(employee_stats["inserted"] + employee_stats["updated"] +
                            attendance_stats["inserted"] + attendance_stats["updated"]),
            status="SUCCESS" if is_success else "FAILED"
        )

        combined_stats = {
            "success": is_success,
            "employees_synced": employee_stats["inserted"] + employee_stats["updated"],
            "employees_inserted": employee_stats["inserted"],
            "employees_updated": employee_stats["updated"],
            "employees_skipped": employee_stats["skipped"],
            "employees_errors": employee_stats["errors"],
            "attendance_synced": attendance_stats["inserted"] + attendance_stats["updated"],
            "attendance_inserted": attendance_stats["inserted"],
            "attendance_updated": attendance_stats["updated"],
            "attendance_skipped": attendance_stats["skipped"],
            "attendance_errors": attendance_stats["errors"],
            "total_execution_time_seconds": execution_time,
            "employee_stats": employee_stats,
            "attendance_stats": attendance_stats
        }

        logger.info(f"Complete sync finished in {execution_time:.2f}s - Combined stats: {combined_stats}")
        return combined_stats

    def calculate_and_cache_kpis(self) -> Dict[str, Any]:
        """Calculate dashboard KPIs from profiles and attendance_daily and write to kpi_cache."""
        import httpx
        try:
            # 1. Fetch employee profiles
            profiles = SupabaseClient.fetch_profiles("EMPLOYEE")
            # Filter active minerva profiles
            active_profiles = [p for p in profiles if p.get("role") == "EMPLOYEE" and (p.get("emp_code") or p.get("minerva_employee_id"))]
            total_employees = len(active_profiles) if active_profiles else len(profiles)
            
            # 2. Fetch daily attendance for today
            today = date.today().isoformat()
            url = f"{settings.SUPABASE_URL}/rest/v1/attendance_daily"
            params = {"attendance_date": f"eq.{today}"}
            
            headers = {
                "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json"
            }
            
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=headers, params=params)
            
            today_records = response.json() if response.status_code == 200 else []
            
            present = sum(1 for r in today_records if str(r.get("attendance_status")).upper() == "PRESENT")
            absent = sum(1 for r in today_records if str(r.get("attendance_status")).upper() == "ABSENT")
            half_day = sum(1 for r in today_records if str(r.get("attendance_status")).upper() == "HALF_DAY")
            late = sum(1 for r in today_records if bool(r.get("late_login_flag")))
            early_logout = sum(1 for r in today_records if bool(r.get("early_logout_flag")))
            
            # Weighted attendance percentage
            attendance_percentage = 0.0
            if total_employees > 0:
                attendance_percentage = round(((present + (half_day * 0.5)) / total_employees) * 100, 2)
                
            active_employees = total_employees
            live_count = sum(1 for r in today_records if r.get("first_punch") is not None or r.get("first_in") is not None)
            
            kpi_data = {
                "total_employees": total_employees,
                "present_today": present,
                "absent_today": absent,
                "late_arrivals": late,
                "early_logout": early_logout,
                "attendance_percentage": attendance_percentage,
                "active_employees": active_employees,
                "live_attendance_count": live_count,
            }
            
            SupabaseClient.upsert_kpi_cache(kpi_data)
            logger.info("KPI cache successfully updated: %s", kpi_data)
            return kpi_data
        except Exception as e:
            logger.error("Failed to calculate and cache KPIs: %s", e)
            raise

    def sync_all_job(self) -> Dict[str, Any]:
        """Unified background sync orchestrator with fallback and logging."""
        logger.info("Starting background synchronization job")
        start_time = datetime.utcnow()
        last_successful_dt = SupabaseClient.fetch_last_successful_sync_time()
        is_incremental = last_successful_dt is not None
        
        # Log attempt in sync_status table
        sync_log = {
            "last_attempt": start_time.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": "RUNNING",
            "records_processed": 0,
            "employees_synced": 0,
            "attendance_synced": 0,
            "duration_ms": 0,
        }
        if last_successful_dt:
            sync_log["last_successful_sync"] = last_successful_dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
            
        # Create initial sync status log
        created_log = SupabaseClient.insert_sync_status(sync_log)
        log_id = created_log.get("id") if isinstance(created_log, dict) else None
        
        employee_stats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
        attendance_stats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
        
        try:
            logger.info("Step 1: Sync Employees")
            employee_stats = self.sync_employees()
            if employee_stats.get("errors", 0) > 0:
                raise ValueError(f"Employee sync had errors: {employee_stats.get('error_details')}")
                
            logger.info("Step 2: Sync Attendance")
            # Incremental sync
            attendance_stats = self.sync_attendance(last_successful_dt)
            if attendance_stats.get("errors", 0) > 0 or not attendance_stats.get("success", True):
                raise ValueError(f"Attendance sync failed: {attendance_stats.get('error_details')}")
                
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            # Recalculate KPIs and cache them
            logger.info("Step 3: Recalculate and Cache KPIs")
            self.calculate_and_cache_kpis()
            
            # Save success state
            final_log = {
                "id": log_id,
                "last_successful_sync": start_time.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
                "last_attempt": start_time.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
                "status": "SUCCESS",
                "records_processed": (employee_stats["inserted"] + employee_stats["updated"] + 
                                     attendance_stats["inserted"] + attendance_stats["updated"]),
                "employees_synced": employee_stats["inserted"] + employee_stats["updated"],
                "attendance_synced": attendance_stats["inserted"] + attendance_stats["updated"],
                "duration_ms": int(duration * 1000),
                "error_message": None,
                "updated_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
            }
            SupabaseClient.insert_sync_status(final_log)
                
            logger.info("Background sync completed successfully in %.2fs", duration)
            return {"success": True, "log": final_log}
            
        except Exception as exc:
            logger.error("Sync attempt failed: %s", exc)
            
            # Full sync fallback!
            if is_incremental:
                logger.warning("Incremental sync failed. Running full sync fallback...")
                try:
                    employee_stats = self.sync_employees()
                    
                    # Full sync (timestamp = None)
                    attendance_stats = self.sync_attendance(last_sync_timestamp=None)
                    
                    if attendance_stats.get("errors", 0) > 0 or not attendance_stats.get("success", True):
                        raise ValueError("Full sync fallback failed as well.")
                        
                    duration = (datetime.utcnow() - start_time).total_seconds()
                    
                    self.calculate_and_cache_kpis()
                    
                    final_log = {
                        "id": log_id,
                        "last_successful_sync": start_time.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
                        "last_attempt": start_time.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
                        "status": "SUCCESS",
                        "records_processed": (employee_stats["inserted"] + employee_stats["updated"] + 
                                             attendance_stats["inserted"] + attendance_stats["updated"]),
                        "employees_synced": employee_stats["inserted"] + employee_stats["updated"],
                        "attendance_synced": attendance_stats["inserted"] + attendance_stats["updated"],
                        "duration_ms": int(duration * 1000),
                        "error_message": f"Incremental failed: {str(exc)}. Full sync fallback succeeded.",
                        "updated_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
                    }
                    SupabaseClient.insert_sync_status(final_log)
                    logger.info("Full sync fallback completed successfully in %.2fs", duration)
                    return {"success": True, "log": final_log}
                    
                except Exception as fallback_exc:
                    logger.error("Full sync fallback failed: %s", fallback_exc)
                    exc = fallback_exc
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            failure_log = {
                "id": log_id,
                "last_attempt": start_time.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
                "status": "FAILED",
                "records_processed": 0,
                "employees_synced": 0,
                "attendance_synced": 0,
                "duration_ms": int(duration * 1000),
                "error_message": str(exc),
                "updated_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
            }
            SupabaseClient.insert_sync_status(failure_log)
            return {"success": False, "error": str(exc)}

    @staticmethod
    def _determine_attendance_status(total_hours: float) -> str:
        """Determine attendance status based on total hours worked."""
        if total_hours >= 8:
            return "PRESENT"
        elif total_hours >= 4:
            return "HALF_DAY"
        elif total_hours > 0:
            return "HALF_DAY"
        else:
            return "ABSENT"


def get_minerva_sync_service() -> MinervaSyncService:
    """Create a validated Minerva sync service instance for runtime use."""
    return MinervaSyncService()
