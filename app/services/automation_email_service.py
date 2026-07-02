import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

import httpx

from app.core.config import settings
from app.services.attendance_service import attendance_service
from app.services.attendance_shift_engine import AttendanceShiftEngine
from app.services.automation_settings_service import automation_settings_service
from app.services.email_preferences_service import email_preferences_service
from app.services.email_reports_service import email_reports_service

logger = logging.getLogger(__name__)

SUPABASE_HEADERS_SERVICE = {
    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}


class AutomationEmailService:
    @staticmethod
    def _previous_completed_month_label(reference: datetime) -> str:
        month = reference.month - 1
        year = reference.year
        if month == 0:
            month = 12
            year -= 1
        return f"{year:04d}-{month:02d}"

    @staticmethod
    def _delivery_target_date(reference: datetime, delay_value: str | None) -> str:
        delay_key = str(delay_value or "same_day").strip().lower()
        if delay_key == "tomorrow":
            return (reference.date() - timedelta(days=1)).isoformat()
        if delay_key == "day_after_tomorrow":
            return (reference.date() - timedelta(days=2)).isoformat()
        return reference.date().isoformat()

    @staticmethod
    def _table_url() -> str:
        return f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/email_logs"

    @staticmethod
    def _safe_json(response: httpx.Response, fallback: Any = None) -> Any:
        body_text = (response.text or "").strip()
        if response.status_code in (200, 201, 204):
            if response.status_code == 204 or not body_text:
                return fallback
            try:
                return response.json()
            except (TypeError, ValueError, json.JSONDecodeError):
                return fallback
        logger.warning("automation email activity fetch failed status=%s body=%s", response.status_code, body_text[:500])
        return fallback

    def _fetch_activity_logs(self, employee_id: str | None = None, email_type: str | None = None) -> List[Dict[str, Any]]:
        params = {"select": "*", "order": "sent_at.desc"}
        if employee_id:
            params["employee_id"] = f"eq.{employee_id}"
        if email_type:
            params["email_type"] = f"eq.{email_type}"

        with httpx.Client(timeout=10.0) as client:
            response = client.get(self._table_url(), headers=SUPABASE_HEADERS_SERVICE, params=params)

        rows = self._safe_json(response, fallback=[])
        return rows if isinstance(rows, list) else []

    @staticmethod
    def _as_date(value: Any) -> date | None:
        if not value:
            return None
        try:
            text = str(value)
            if "T" in text or " " in text:
                return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return None

    def _as_month(self, value: Any) -> str | None:
        if not value:
            return None
        text = str(value).strip()
        if len(text) == 7 and text[4] == "-" and text[:4].isdigit() and text[5:7].isdigit():
            return text
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            return text[:7]
        return None

    def _month_label_for(self, target_month: str) -> str | None:
        if not target_month or len(target_month) != 7 or target_month[4] != "-":
            return None
        try:
            year = int(target_month[:4])
            month = int(target_month[5:7])
            return datetime(year, month, 1).strftime("%B %Y")
        except ValueError:
            return None

    def _has_sent_monthly_report(self, employee_id: str, target_month: str) -> bool:
        if not target_month:
            return False
        target_label = self._month_label_for(target_month)
        if not target_label:
            return False
        rows = self._fetch_activity_logs(employee_id=employee_id, email_type="monthly_report")
        for row in rows:
            subject = str(row.get("subject") or "")
            if target_label in subject and str(row.get("status") or "").upper() in {"SENT", "PENDING"}:
                return True
        return False

    def _monthly_report_subject(self, target_month: str | None, context: Dict[str, Any] | None = None) -> str:
        if target_month:
            month_label = self._month_label_for(target_month)
            if month_label:
                return f"Monthly Attendance Report – {month_label}"
        return email_reports_service._subject_for("monthly_report", context or {})

    def send_monthly_reports(self, target_month: str | None = None) -> List[Dict[str, Any]]:
        import calendar
        import traceback
        month_label = target_month or date.today().replace(day=1).isoformat()[:7]
        
        try:
            year = int(month_label[:4])
            month = int(month_label[5:7])
            last_day = calendar.monthrange(year, month)[1]
        except (ValueError, IndexError) as e:
            logger.warning("Failed to parse month_label %s, defaulting to 30 days: %s", month_label, e)
            last_day = 30
            
        start_date = f"{month_label}-01"
        end_date = f"{month_label}-{last_day:02d}"
        logger.info("Fetching attendance for monthly report | function=send_monthly_reports | start_date=%s | end_date=%s", start_date, end_date)
        
        try:
            records = attendance_service.get_all_attendance(limit=1000, start_date=start_date, end_date=end_date).get("records", [])
        except Exception as exc:
            logger.error(
                "Failed to fetch attendance records inside send_monthly_reports | function=send_monthly_reports | month=%s | start_date=%s | end_date=%s | error=%s | traceback=%s",
                month_label, start_date, end_date, str(exc), traceback.format_exc()
            )
            records = []
            
        sent = []
        processed_employee_ids: set[str] = set()

        for record in records:
            employee_id = str(record.get("employee_id") or "")
            if not employee_id or employee_id in processed_employee_ids:
                continue
            employee_name = str(record.get("employee_name") or "Employee")
            recipient_email = str(record.get("employee_email") or record.get("recipient_email") or "")
            attendance_date = f"{month_label}-01"
            subject = self._monthly_report_subject(month_label, {"employee_id": employee_id, "employee_name": employee_name, "month": int(month_label[5:7]), "year": int(month_label[:4])})
            if email_reports_service._find_existing_monthly_report(employee_id, subject):
                processed_employee_ids.add(employee_id)
                continue
            activity = self._send_if_enabled(employee_id, employee_name, recipient_email, "monthly_report", attendance_date)
            if activity:
                sent.append(activity)
            processed_employee_ids.add(employee_id)
        return sent

    def should_send_alert(self, employee_id: str, attendance_date: str, email_type: str) -> bool:
        if str(email_type).lower() == "monthly_report":
            target_month = self._as_month(attendance_date)
            return not self._has_sent_monthly_report(employee_id, target_month or "")

        rows = self._fetch_activity_logs(employee_id=employee_id, email_type=email_type)
        target_day = self._as_date(attendance_date)
        for row in rows:
            sent_at = self._as_date(row.get("sent_at"))
            if sent_at == target_day and str(row.get("status") or "").upper() in {"SENT", "PENDING"}:
                return False
        return True

    def _preference_mode(self, preferences: List[Dict[str, Any]], employee_id: str, mode_name: str) -> str:
        for row in preferences:
            if str(row.get("employee_id") or "") == str(employee_id):
                return str(row.get(mode_name) or "auto").lower()
        return "auto"

    def _attendance_record_is_complete(self, record: Dict[str, Any] | None) -> bool:
        return bool(record and record.get("first_punch") and record.get("last_punch"))

    def _fetch_normalized_record(self, employee_id: str, attendance_date: str) -> Dict[str, Any] | None:
        if not employee_id or not attendance_date:
            return None

        daily_records = attendance_service.get_daily_attendance(limit=1, employee_id=employee_id, start_date=attendance_date, end_date=attendance_date).get("records", [])
        if daily_records:
            return daily_records[0]

        record_list = attendance_service.get_all_attendance(limit=1, employee_id=employee_id, start_date=attendance_date, end_date=attendance_date).get("records", [])
        return record_list[0] if record_list else None

    def _send_if_enabled(self, employee_id: str, employee_name: str, recipient_email: str, email_type: str, attendance_date: str) -> Dict[str, Any] | None:
        if not recipient_email:
            return None
        if not self.should_send_alert(employee_id, attendance_date, email_type):
            return {"status": "skipped", "reason": "duplicate"}

        # Check employee-level communication settings (preferences)
        try:
            prefs = email_preferences_service.get_preference(employee_id)
        except Exception as p_exc:
            logger.warning("Failed to load employee preferences for %s: %s", employee_id, p_exc)
            prefs = None

        if email_type == "monthly_report":
            mode = (prefs or {}).get("monthly_report_mode") or "manual"
            if mode != "auto":
                logger.info("Skipping monthly report for %s: employee preference is not auto", employee_id)
                return {"status": "skipped", "reason": "employee_preference_manual"}
        elif email_type == "late_login_alert":
            mode = (prefs or {}).get("late_login_mode") or "manual"
            if mode != "auto":
                logger.info("Skipping late login alert for %s: employee preference is not auto", employee_id)
                return {"status": "skipped", "reason": "employee_preference_manual"}
        elif email_type == "early_logout_alert":
            mode = (prefs or {}).get("early_logout_mode") or "manual"
            if mode != "auto":
                logger.info("Skipping early logout alert for %s: employee preference is not auto", employee_id)
                return {"status": "skipped", "reason": "employee_preference_manual"}

        # Resolve dynamic email and CC email from active shift assignment
        recipient_email, cc_email = email_reports_service.resolve_employee_emails(employee_id, recipient_email)

        try:
            record = self._fetch_normalized_record(employee_id, attendance_date)
            if email_type in {"late_login_alert", "early_logout_alert"} and not self._attendance_record_is_complete(record):
                return None
            classification = AttendanceShiftEngine.classify_record(record) if record else {}
            month = int(attendance_date[5:7]) if isinstance(attendance_date, str) and len(attendance_date) >= 7 and attendance_date[4] == "-" else None
            year = int(attendance_date[:4]) if isinstance(attendance_date, str) and len(attendance_date) >= 4 else None
            context = {
                "employee_id": employee_id,
                "employee_name": employee_name,
                "attendance_date": attendance_date,
                "record": record,
                "classification": classification,
                "month": month,
                "year": year,
                "month_label": f"{datetime(year, month, 1).strftime('%B %Y')}" if month and year else None,
            }
            return email_reports_service.log_activity(
                employee_id=str(employee_id),
                employee_name=str(employee_name or "Employee"),
                recipient_email=str(recipient_email or ""),
                cc_email=str(cc_email or ""),
                email_type=email_type,
                status="SENT",
                skip_send=False,
                context=context,
                source="AUTOMATION",
            )
        except Exception as exc:
            logger.exception("Failed sending automated email for %s", employee_id)
            try:
                email_reports_service.log_activity(
                    employee_id=str(employee_id),
                    employee_name=str(employee_name or "Employee"),
                    recipient_email=str(recipient_email or ""),
                    cc_email=str(cc_email or ""),
                    email_type=email_type,
                    status="FAILED",
                    skip_send=True,
                    source="AUTOMATION",
                )
            except Exception:
                pass
            raise RuntimeError(f"Automated email delivery failed: {exc}") from exc

    def send_late_login_alerts(self, attendance_date: str | None = None) -> List[Dict[str, Any]]:
        from app.services.dashboard_analytics_service import DashboardAnalyticsService
        target_date = attendance_date or date.today().isoformat()
        
        # Tracking logs
        eligible_count = 0
        sent_count = 0
        skipped_count = 0
        skip_reasons = {}
        
        year = int(target_date[:4])
        month = int(target_date[5:7])
        
        try:
            all_records = DashboardAnalyticsService._fetch_records("attendance_records")
            records = [r for r in all_records if str(r.get("attendance_date", "")) == target_date]
        except Exception as exc:
            import traceback
            # Bug 5 requirement: Log Employee ID, Month, Year, Date Range, SQL/API Query, HTTP Status, Full Exception, Stack Trace
            logger.error(
                "Attendance fetch failed for Late Logins:\n"
                "Employee ID: ALL\n"
                "Month: %s\n"
                "Year: %s\n"
                "Date Range: %s\n"
                "SQL/API Query: GET %s/rest/v1/attendance_daily\n"
                "HTTP Status: Unknown\n"
                "Full Exception: %s\n"
                "Stack Trace:\n%s",
                month, year, target_date, settings.SUPABASE_URL, str(exc), traceback.format_exc()
            )
            raise

        sent = []
        eligible_count = len(records)

        for record in records:
            employee_id = str(record.get("employee_id") or "")
            employee_name = str(record.get("employee_name") or "Employee")
            
            # Bug 7: Recipient and CC emails resolved directly from Shift Management
            recipient_email, cc_email = email_reports_service.resolve_employee_emails(employee_id, "", "")
            
            if not self._attendance_record_is_complete(record):
                skipped_count += 1
                skip_reasons["Incomplete Record"] = skip_reasons.get("Incomplete Record", 0) + 1
                continue
                
            classification = AttendanceShiftEngine.classify_record(record)
            if not classification.get("is_late"):
                skipped_count += 1
                skip_reasons["Not Late"] = skip_reasons.get("Not Late", 0) + 1
                continue
                
            try:
                prefs = email_preferences_service.get_preference(employee_id)
            except Exception as p_exc:
                logger.warning("Failed to load employee preferences for %s: %s", employee_id, p_exc)
                prefs = None

            mode = (prefs or {}).get("late_login_mode") or "manual"
            if mode != "auto":
                skipped_count += 1
                skip_reasons["Preference Manual"] = skip_reasons.get("Preference Manual", 0) + 1
                continue
                
            if not recipient_email:
                skipped_count += 1
                skip_reasons["Email Missing"] = skip_reasons.get("Email Missing", 0) + 1
                continue
                
            if not self.should_send_alert(employee_id, target_date, "late_login_alert"):
                skipped_count += 1
                skip_reasons["Already Sent"] = skip_reasons.get("Already Sent", 0) + 1
                continue
                
            try:
                activity = self._send_if_enabled(employee_id, employee_name, recipient_email, "late_login_alert", target_date)
                if activity:
                    sent.append(activity)
                    sent_count += 1
            except Exception as send_exc:
                logger.error("Failed to send late login alert to %s: %s", employee_id, send_exc)
                skipped_count += 1
                skip_reasons[f"Error: {str(send_exc)}"] = skip_reasons.get(f"Error: {str(send_exc)}", 0) + 1
                
        logger.info(
            "Late Login Automation Execution Summary | Eligible Employees: %s | Employees Sent: %s | Employees Skipped: %s | Reasons: %s",
            eligible_count, sent_count, skipped_count, json.dumps(skip_reasons)
        )
        return sent

    def send_early_logout_alerts(self, attendance_date: str | None = None) -> List[Dict[str, Any]]:
        from app.services.dashboard_analytics_service import DashboardAnalyticsService
        target_date = attendance_date or date.today().isoformat()
        
        # Tracking logs
        eligible_count = 0
        sent_count = 0
        skipped_count = 0
        skip_reasons = {}
        
        year = int(target_date[:4])
        month = int(target_date[5:7])
        
        try:
            all_records = DashboardAnalyticsService._fetch_records("attendance_records")
            records = [r for r in all_records if str(r.get("attendance_date", "")) == target_date]
        except Exception as exc:
            import traceback
            logger.error(
                "Attendance fetch failed for Early Logouts:\n"
                "Employee ID: ALL\n"
                "Month: %s\n"
                "Year: %s\n"
                "Date Range: %s\n"
                "SQL/API Query: GET %s/rest/v1/attendance_daily\n"
                "HTTP Status: Unknown\n"
                "Full Exception: %s\n"
                "Stack Trace:\n%s",
                month, year, target_date, settings.SUPABASE_URL, str(exc), traceback.format_exc()
            )
            raise

        sent = []
        eligible_count = len(records)

        for record in records:
            employee_id = str(record.get("employee_id") or "")
            employee_name = str(record.get("employee_name") or "Employee")
            
            # Bug 7: Recipient and CC emails resolved directly from Shift Management
            recipient_email, cc_email = email_reports_service.resolve_employee_emails(employee_id, "", "")
            
            if not self._attendance_record_is_complete(record):
                skipped_count += 1
                skip_reasons["Incomplete Record"] = skip_reasons.get("Incomplete Record", 0) + 1
                continue
                
            classification = AttendanceShiftEngine.classify_record(record)
            if not classification.get("is_early_out"):
                skipped_count += 1
                skip_reasons["Not Early Out"] = skip_reasons.get("Not Early Out", 0) + 1
                continue
                
            try:
                prefs = email_preferences_service.get_preference(employee_id)
            except Exception as p_exc:
                logger.warning("Failed to load employee preferences for %s: %s", employee_id, p_exc)
                prefs = None

            mode = (prefs or {}).get("early_logout_mode") or "manual"
            if mode != "auto":
                skipped_count += 1
                skip_reasons["Preference Manual"] = skip_reasons.get("Preference Manual", 0) + 1
                continue
                
            if not recipient_email:
                skipped_count += 1
                skip_reasons["Email Missing"] = skip_reasons.get("Email Missing", 0) + 1
                continue
                
            if not self.should_send_alert(employee_id, target_date, "early_logout_alert"):
                skipped_count += 1
                skip_reasons["Already Sent"] = skip_reasons.get("Already Sent", 0) + 1
                continue
                
            try:
                activity = self._send_if_enabled(employee_id, employee_name, recipient_email, "early_logout_alert", target_date)
                if activity:
                    sent.append(activity)
                    sent_count += 1
            except Exception as send_exc:
                logger.error("Failed to send early logout alert to %s: %s", employee_id, send_exc)
                skipped_count += 1
                skip_reasons[f"Error: {str(send_exc)}"] = skip_reasons.get(f"Error: {str(send_exc)}", 0) + 1
                
        logger.info(
            "Early Logout Automation Execution Summary | Eligible Employees: %s | Employees Sent: %s | Employees Skipped: %s | Reasons: %s",
            eligible_count, sent_count, skipped_count, json.dumps(skip_reasons)
        )
        return sent

    def process_due_jobs(self) -> Dict[str, Any]:
        from zoneinfo import ZoneInfo
        kolkata_tz = ZoneInfo("Asia/Kolkata")
        now = datetime.now(kolkata_tz)
        
        logger.info("Scheduler Started | Current Time: %s", now.strftime("%Y-%m-%d %H:%M:%S %Z"))
        
        try:
            settings_payload = automation_settings_service.get_settings()
        except Exception as exc:
            logger.error("Failed to load automation settings: %s", exc)
            settings_payload = {}

        results = {"processed": False, "monthly_report": 0, "late_login_alert": 0, "early_logout_alert": 0}

        # Independent execution block: Monthly reports
        try:
            monthly_result = self.run_monthly_report_job(now=now, settings_payload=settings_payload)
            if monthly_result.get("processed"):
                results["monthly_report"] = int(monthly_result.get("count", 0))
                results["processed"] = True
        except Exception as exc:
            logger.error("Monthly report runner failed: %s", exc)

        # Independent execution block: Late logins
        try:
            late_result = self.run_late_login_job(now=now, settings_payload=settings_payload)
            if late_result.get("processed"):
                results["late_login_alert"] = int(late_result.get("count", 0))
                results["processed"] = True
        except Exception as exc:
            logger.error("Late login runner failed: %s", exc)

        # Independent execution block: Early logouts
        try:
            early_result = self.run_early_logout_job(now=now, settings_payload=settings_payload)
            if early_result.get("processed"):
                results["early_logout_alert"] = int(early_result.get("count", 0))
                results["processed"] = True
        except Exception as exc:
            logger.error("Early logout runner failed: %s", exc)

        return results

    def run_monthly_report_job(self, now: datetime | None = None, settings_payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        from zoneinfo import ZoneInfo
        kolkata_tz = ZoneInfo("Asia/Kolkata")
        now = now or datetime.now(kolkata_tz)
        settings_payload = settings_payload or automation_settings_service.get_settings()
        
        enabled = bool(settings_payload.get("monthly_report_enabled"))
        current_day = now.day
        gen_day = int(settings_payload.get("monthly_report_day", 5))
        current_time = now.strftime("%H:%M")
        del_time = str(settings_payload.get("monthly_report_time", "09:00"))
        
        logger.info(
            "Monthly Automation Check | Enabled: %s | Current Day: %s | Generation Day: %s | Current Time: %s | Delivery Time: %s",
            enabled, current_day, gen_day, current_time, del_time
        )
        
        if not enabled:
            logger.info("Monthly Automation Skipped: Disabled")
            return {"processed": False, "reason": "disabled", "count": 0}
        if current_day != gen_day:
            logger.info("Monthly Automation Skipped: Wrong Generation Day")
            return {"processed": False, "reason": "not_scheduled_day", "count": 0}
        if current_time < del_time:
            logger.info("Monthly Automation Skipped: Wrong Delivery Time (not due yet)")
            return {"processed": False, "reason": "not_due_yet", "count": 0}

        try:
            target_month = self._previous_completed_month_label(now)
            execution_date = now.date().isoformat()
            
            try:
                url_exec = f"{settings.SUPABASE_URL}/rest/v1/automation_job_executions"
                headers_exec = {
                    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                }
                params_exec = {
                    "job_type": "eq.monthly_report",
                    "execution_date": f"eq.{execution_date}",
                    "status": "in.(SUCCESS,SKIPPED)"
                }
                resp_exec = httpx.get(url_exec, headers=headers_exec, params=params_exec)
                if resp_exec.status_code == 200 and resp_exec.json():
                    logger.info("Monthly Automation Skipped: Already executed today")
                    return {"processed": False, "reason": "already_executed_today", "count": 0}
            except Exception as e_exec:
                logger.warning("Failed to check job execution log: %s", e_exec)

            from app.services.automation_job_log_service import automation_job_log_service
            claimed = automation_job_log_service.claim_job("monthly_report", execution_date)
            if not claimed:
                logger.info("Monthly Automation Skipped: Already claimed/running")
                return {"processed": False, "reason": "already_claimed", "count": 0}
                
            sent = self.send_monthly_reports(target_month)
            logger.info("Monthly report job completed count=%s target_month=%s", len(sent), target_month)
            
            status_val = "SUCCESS" if sent else "SKIPPED"
            automation_job_log_service.finalize_job("monthly_report", execution_date, status_val, details={"count": len(sent)})
            return {"processed": True, "count": len(sent), "target_month": target_month}
        except Exception as exc:
            logger.warning("Monthly report job failed: %s", exc)
            return {"processed": False, "reason": str(exc), "count": 0}

    def run_late_login_job(self, now: datetime | None = None, settings_payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        from zoneinfo import ZoneInfo
        kolkata_tz = ZoneInfo("Asia/Kolkata")
        now = now or datetime.now(kolkata_tz)
        settings_payload = settings_payload or automation_settings_service.get_settings()
        
        enabled = bool(settings_payload.get("late_login_enabled"))
        current_time = now.strftime("%H:%M")
        del_time = str(settings_payload.get("late_login_time", "18:00"))
        
        logger.info(
            "Late Login Automation Check | Enabled: %s | Current Time: %s | Delivery Time: %s",
            enabled, current_time, del_time
        )
        
        if not enabled:
            logger.info("Late Login Automation Skipped: Disabled")
            return {"processed": False, "reason": "disabled", "count": 0}
        if current_time < del_time:
            logger.info("Late Login Automation Skipped: Wrong Delivery Time (not due yet)")
            return {"processed": False, "reason": "not_due_yet", "count": 0}

        try:
            target_date = self._delivery_target_date(now, settings_payload.get("late_login_delay"))
            execution_date = now.date().isoformat()
            
            try:
                url_exec = f"{settings.SUPABASE_URL}/rest/v1/automation_job_executions"
                headers_exec = {
                    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                }
                params_exec = {
                    "job_type": "eq.late_login",
                    "execution_date": f"eq.{execution_date}",
                    "status": "in.(SUCCESS,SKIPPED)"
                }
                resp_exec = httpx.get(url_exec, headers=headers_exec, params=params_exec)
                if resp_exec.status_code == 200 and resp_exec.json():
                    logger.info("Late Login Automation Skipped: Already executed today")
                    return {"processed": False, "reason": "already_executed_today", "count": 0}
            except Exception as e_exec:
                logger.warning("Failed to check job execution log: %s", e_exec)
                
            from app.services.automation_job_log_service import automation_job_log_service
            claimed = automation_job_log_service.claim_job("late_login", execution_date)
            if not claimed:
                logger.info("Late Login Automation Skipped: Already claimed/running")
                return {"processed": False, "reason": "already_claimed", "count": 0}
                
            sent = self.send_late_login_alerts(target_date)
            logger.info("Late login job completed count=%s target_date=%s", len(sent), target_date)
            
            status_val = "SUCCESS" if sent else "SKIPPED"
            automation_job_log_service.finalize_job("late_login", execution_date, status_val, details={"count": len(sent)})
            return {"processed": True, "count": len(sent), "target_date": target_date}
        except Exception as exc:
            logger.warning("Late login job failed: %s", exc)
            return {"processed": False, "reason": str(exc), "count": 0}

    def run_early_logout_job(self, now: datetime | None = None, settings_payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        from zoneinfo import ZoneInfo
        kolkata_tz = ZoneInfo("Asia/Kolkata")
        now = now or datetime.now(kolkata_tz)
        settings_payload = settings_payload or automation_settings_service.get_settings()
        
        enabled = bool(settings_payload.get("early_logout_enabled"))
        current_time = now.strftime("%H:%M")
        del_time = str(settings_payload.get("early_logout_time", "22:30"))
        
        logger.info(
            "Early Logout Automation Check | Enabled: %s | Current Time: %s | Delivery Time: %s",
            enabled, current_time, del_time
        )
        
        if not enabled:
            logger.info("Early Logout Automation Skipped: Disabled")
            return {"processed": False, "reason": "disabled", "count": 0}
        if current_time < del_time:
            logger.info("Early Logout Automation Skipped: Wrong Delivery Time (not due yet)")
            return {"processed": False, "reason": "not_due_yet", "count": 0}

        try:
            target_date = self._delivery_target_date(now, settings_payload.get("early_logout_delay"))
            execution_date = now.date().isoformat()
            
            try:
                url_exec = f"{settings.SUPABASE_URL}/rest/v1/automation_job_executions"
                headers_exec = {
                    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                }
                params_exec = {
                    "job_type": "eq.early_logout",
                    "execution_date": f"eq.{execution_date}",
                    "status": "in.(SUCCESS,SKIPPED)"
                }
                resp_exec = httpx.get(url_exec, headers=headers_exec, params=params_exec)
                if resp_exec.status_code == 200 and resp_exec.json():
                    logger.info("Early Logout Automation Skipped: Already executed today")
                    return {"processed": False, "reason": "already_executed_today", "count": 0}
            except Exception as e_exec:
                logger.warning("Failed to check job execution log: %s", e_exec)
                
            from app.services.automation_job_log_service import automation_job_log_service
            claimed = automation_job_log_service.claim_job("early_logout", execution_date)
            if not claimed:
                logger.info("Early Logout Automation Skipped: Already claimed/running")
                return {"processed": False, "reason": "already_claimed", "count": 0}
                
            sent = self.send_early_logout_alerts(target_date)
            logger.info("Early logout job completed count=%s target_date=%s", len(sent), target_date)
            
            status_val = "SUCCESS" if sent else "SKIPPED"
            automation_job_log_service.finalize_job("early_logout", execution_date, status_val, details={"count": len(sent)})
            return {"processed": True, "count": len(sent), "target_date": target_date}
        except Exception as exc:
            logger.warning("Early logout job failed: %s", exc)
            return {"processed": False, "reason": str(exc), "count": 0}


automation_email_service = AutomationEmailService()
