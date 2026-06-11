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

    def should_send_alert(self, employee_id: str, attendance_date: str, email_type: str) -> bool:
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
                return str(row.get(mode_name) or "manual").lower()
        return "manual"

    def _send_if_enabled(self, employee_id: str, employee_name: str, recipient_email: str, email_type: str, attendance_date: str) -> Dict[str, Any] | None:
        if not recipient_email:
            return None
        preferences = email_preferences_service.list_preferences()
        mode = self._preference_mode(preferences, employee_id, {
            "monthly_report": "monthly_report_mode",
            "late_login_alert": "late_login_mode",
            "early_logout_alert": "early_logout_mode",
        }.get(email_type, "late_login_mode"))
        if mode != "auto":
            return None
        if not self.should_send_alert(employee_id, attendance_date, email_type):
            return {"status": "skipped", "reason": "duplicate"}
        try:
            record = None
            if attendance_date:
                record_list = attendance_service.get_all_attendance(limit=1, employee_id=employee_id, start_date=attendance_date, end_date=attendance_date).get("records", [])
                if record_list:
                    record = record_list[0]
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
            message_id = email_reports_service.send_email(
                recipient_email=str(recipient_email),
                subject=email_reports_service._subject_for(email_type, context),
                email_body=email_reports_service._body_for(employee_name, email_type, context),
                email_type=email_type,
                employee_name=str(employee_name or "Employee"),
            )
            return email_reports_service.log_activity(
                employee_id=str(employee_id),
                employee_name=str(employee_name or "Employee"),
                recipient_email=str(recipient_email),
                email_type=email_type,
                status="SENT",
                provider_message_id=message_id,
                skip_send=True,
            )
        except Exception as exc:
            email_reports_service.log_activity(
                employee_id=str(employee_id),
                employee_name=str(employee_name or "Employee"),
                recipient_email=str(recipient_email),
                email_type=email_type,
                status="FAILED",
                provider="resend",
                provider_message_id=None,
                skip_send=True,
            )
            raise RuntimeError(f"Resend email delivery failed: {exc}") from exc

    def send_monthly_reports(self, target_month: str | None = None) -> List[Dict[str, Any]]:
        month_label = target_month or date.today().replace(day=1).isoformat()[:7]
        records = attendance_service.get_all_attendance(limit=1000, start_date=f"{month_label}-01", end_date=f"{month_label}-31").get("records", [])
        sent = []
        for record in records:
            employee_id = str(record.get("employee_id") or "")
            employee_name = str(record.get("employee_name") or "Employee")
            recipient_email = str(record.get("employee_email") or record.get("recipient_email") or "")
            attendance_date = str(record.get("attendance_date") or month_label)
            activity = self._send_if_enabled(employee_id, employee_name, recipient_email, "monthly_report", attendance_date)
            if activity:
                sent.append(activity)
        return sent

    def send_late_login_alerts(self, attendance_date: str | None = None) -> List[Dict[str, Any]]:
        target_date = attendance_date or date.today().isoformat()
        records = attendance_service.get_all_attendance(limit=1000, start_date=target_date, end_date=target_date).get("records", [])
        sent = []
        for record in records:
            classification = AttendanceShiftEngine.classify_record(record)
            if not classification.get("is_late"):
                continue
            employee_id = str(record.get("employee_id") or "")
            employee_name = str(record.get("employee_name") or "Employee")
            recipient_email = str(record.get("employee_email") or record.get("recipient_email") or "")
            activity = self._send_if_enabled(employee_id, employee_name, recipient_email, "late_login_alert", target_date)
            if activity:
                sent.append(activity)
        return sent

    def send_early_logout_alerts(self, attendance_date: str | None = None) -> List[Dict[str, Any]]:
        target_date = attendance_date or date.today().isoformat()
        records = attendance_service.get_all_attendance(limit=1000, start_date=target_date, end_date=target_date).get("records", [])
        sent = []
        for record in records:
            classification = AttendanceShiftEngine.classify_record(record)
            if not classification.get("is_early_out"):
                continue
            employee_id = str(record.get("employee_id") or "")
            employee_name = str(record.get("employee_name") or "Employee")
            recipient_email = str(record.get("employee_email") or record.get("recipient_email") or "")
            activity = self._send_if_enabled(employee_id, employee_name, recipient_email, "early_logout_alert", target_date)
            if activity:
                sent.append(activity)
        return sent

    def process_due_jobs(self) -> Dict[str, Any]:
        settings_payload = automation_settings_service.get_settings()
        now = datetime.now()
        today = now.date().isoformat()
        results = {"processed": False, "monthly_report": 0, "late_login_alert": 0, "early_logout_alert": 0}

        if bool(settings_payload.get("monthly_report_enabled")) and now.day == int(settings_payload.get("monthly_report_day", 5)) and now.strftime("%H:%M") >= str(settings_payload.get("monthly_report_time", "09:00")):
            target_month = self._previous_completed_month_label(now)
            results["monthly_report"] = len(self.send_monthly_reports(target_month))
            results["processed"] = True

        if bool(settings_payload.get("late_login_enabled")) and now.strftime("%H:%M") >= str(settings_payload.get("late_login_time", "18:00")):
            target_date = self._delivery_target_date(now, settings_payload.get("late_login_delay"))
            results["late_login_alert"] = len(self.send_late_login_alerts(target_date))
            results["processed"] = True

        if bool(settings_payload.get("early_logout_enabled")) and now.strftime("%H:%M") >= str(settings_payload.get("early_logout_time", "22:30")):
            target_date = self._delivery_target_date(now, settings_payload.get("early_logout_delay"))
            results["early_logout_alert"] = len(self.send_early_logout_alerts(target_date))
            results["processed"] = True

        return results


automation_email_service = AutomationEmailService()
