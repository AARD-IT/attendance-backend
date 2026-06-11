import base64
import csv
import html
import io
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict

import httpx

from app.core.config import settings
from app.services.attendance_service import attendance_service
from app.services.attendance_shift_engine import AttendanceShiftEngine
from app.services.dashboard_analytics_service import analytics_service
from app.services.shift_assignment_service import shift_assignment_service
from app.services.shift_rules import get_shift_rule, normalize_shift_type

logger = logging.getLogger(__name__)

SUPABASE_HEADERS_SERVICE = {
    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}


def _format_time(value: Any) -> str:
    if not value:
        return "--"
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed.strftime("%H:%M")
    except ValueError:
        return str(value)


def _safe_text(value: Any) -> str:
    return str(value or "").strip() or "--"


def _previous_completed_month(reference_month: int | None = None, reference_year: int | None = None) -> tuple[int, int]:
    now = datetime.now()
    month = reference_month or now.month
    year = reference_year or now.year
    if month == 1:
        return 12, year - 1
    return month - 1, year


class EmailReportsService:
    @staticmethod
    def _table_url() -> str:
        return f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/email_logs"

    @staticmethod
    def _subject_for(email_type: str, context: Dict[str, Any] | None = None) -> str:
        normalized = str(email_type or "").lower()
        if normalized == "monthly_report":
            month = context.get("month_label")
            if not month:
                month_value, year_value = _previous_completed_month(context.get("month"), context.get("year"))
                month = datetime(year_value, month_value, 1).strftime("%B %Y")
            return f"Monthly Attendance Report – {month}"
        if normalized == "late_login_alert":
            return "Attendance Late Login Alert"
        if normalized == "early_logout_alert":
            return "Attendance Early Logout Alert"
        label = normalized.replace("_", " ").title()
        return f"Attendance {label}"

    @staticmethod
    def _fetch_ceo_email() -> str:
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/profiles", headers=SUPABASE_HEADERS_SERVICE)
            if response.status_code != 200:
                return ""
            for row in response.json() or []:
                if str(row.get("role") or "").upper() == "CEO":
                    email = str(row.get("email") or "").strip()
                    if email:
                        return email
        except Exception:
            return ""
        return ""

    @staticmethod
    def _resolve_assignment(record: Dict[str, Any] | None) -> Dict[str, Any]:
        if not isinstance(record, dict) or not record:
            return {}
        resolved = AttendanceShiftEngine.resolve_shift_assignment(record) or {}
        if resolved.get("shift_name") or resolved.get("shift_type"):
            return resolved

        employee_id = str(record.get("employee_id") or "")
        attendance_date = str(record.get("attendance_date") or "")
        if not employee_id or not attendance_date:
            return resolved

        assignments = shift_assignment_service.get_assignments() or []
        for item in assignments:
            if str(item.get("employee_id") or "") != employee_id:
                continue
            start_date = str(item.get("start_date") or item.get("effective_from") or "")
            end_date = str(item.get("end_date") or item.get("effective_to") or "")
            if start_date and attendance_date and attendance_date < start_date:
                continue
            if end_date and attendance_date and attendance_date > end_date:
                continue
            return dict(item)
        return resolved

    @staticmethod
    def _resolve_shift_timings(record: Dict[str, Any], assignment: Dict[str, Any] | None = None, classification: Dict[str, Any] | None = None) -> Dict[str, Any]:
        assignment = assignment or {}
        classification = classification or {}
        shift_source = (
            assignment.get("shift_type")
            or assignment.get("shift_name")
            or record.get("shift_type")
            or record.get("shift_name")
            or classification.get("shift_type")
            or "Shift 1"
        )
        rule = get_shift_rule(normalize_shift_type(str(shift_source)))
        return {
            "shift_name": str(assignment.get("shift_name") or assignment.get("shift_type") or record.get("shift_name") or record.get("shift_type") or shift_source or "Assigned Shift"),
            "shift_type": normalize_shift_type(str(shift_source)),
            "login_cutoff": str(rule.get("login_cutoff") or assignment.get("login_cutoff") or classification.get("login_cutoff") or "10:35"),
            "logout_cutoff": str(rule.get("logout_cutoff") or assignment.get("logout_cutoff") or classification.get("logout_cutoff") or "18:00"),
        }

    @staticmethod
    def build_late_login_email(context: Dict[str, Any]) -> str:
        employee_name = _safe_text(context.get("employee_name") or "Employee")
        attendance_date = context.get("attendance_date") or datetime.now().date().isoformat()
        record = context.get("record") or {}
        classification = context.get("classification") or AttendanceShiftEngine.classify_record(record)
        assignment = context.get("assignment") or EmailReportsService._resolve_assignment(record)
        shift_context = EmailReportsService._resolve_shift_timings(record, assignment, classification)
        shift_name = shift_context["shift_name"]
        login_cutoff = _safe_text(shift_context["login_cutoff"])
        logout_cutoff = _safe_text(shift_context["logout_cutoff"])
        shift_timing = f"Login by {login_cutoff}, Logout by {logout_cutoff}"
        expected_login = login_cutoff
        actual_login = _format_time(record.get("first_punch"))
        login_deviations = int(context.get("login_deviations") or 0)
        logout_deviations = int(context.get("logout_deviations") or 0)
        escalations = int(context.get("escalations") or (login_deviations + logout_deviations) // 3)

        return f"""
        <html><body style=\"font-family:Arial,Helvetica,sans-serif;color:#111827;line-height:1.5;\">
          <p>Dear {html.escape(employee_name)},</p>
          <p>This email is regarding your attendance on {html.escape(str(attendance_date))}. Our records indicate that you logged in later than the assigned login cutoff for this shift.</p>
          <h3 style=\"margin-bottom:8px;\">Attendance Details</h3>
          <table cellpadding=\"6\" cellspacing=\"0\" style=\"border-collapse:collapse;\">
            <tr><td><strong>Employee Name</strong></td><td>{html.escape(employee_name)}</td></tr>
            <tr><td><strong>Attendance Date</strong></td><td>{html.escape(str(attendance_date))}</td></tr>
            <tr><td><strong>Assigned Shift</strong></td><td>{html.escape(shift_name)}</td></tr>
            <tr><td><strong>Shift Timing</strong></td><td>{html.escape(shift_timing)}</td></tr>
            <tr><td><strong>Expected Login Time</strong></td><td>{html.escape(expected_login)}</td></tr>
            <tr><td><strong>Actual Login Time</strong></td><td>{html.escape(actual_login)}</td></tr>
          </table>
          <h3 style=\"margin-top:16px;\">Observation</h3>
          <p>As per your assigned shift schedule, your login cutoff time was <strong>{html.escape(expected_login)}</strong>.</p>
          <p>However, your attendance record shows that you logged in at <strong>{html.escape(actual_login)}</strong>, which has resulted in a Login Deviation.</p>
          <h3 style=\"margin-top:16px;\">Deviation Summary</h3>
          <table cellpadding=\"6\" cellspacing=\"0\" style=\"border-collapse:collapse;\">
            <tr><td><strong>Login Deviation Added</strong></td><td>1</td></tr>
            <tr><td><strong>Current Total Login Deviations</strong></td><td>{login_deviations}</td></tr>
            <tr><td><strong>Current Total Logout Deviations</strong></td><td>{logout_deviations}</td></tr>
            <tr><td><strong>Current Escalations</strong></td><td>{escalations}</td></tr>
          </table>
          <p style=\"margin-top:12px;\"><strong>Attendance Policy</strong></p>
          <ul>
            <li>1 Late Login = 1 Login Deviation</li>
            <li>1 Early Logout = 1 Logout Deviation</li>
            <li>Every 3 Deviations = 1 Escalation</li>
            <li>Every 3 Escalations = ₹1000 Fine</li>
          </ul>
          <p>Kindly ensure that you follow your assigned shift timings and avoid further attendance deviations.</p>
          <p>Please reply to this email if you believe there is any discrepancy in the attendance record.</p>
          <p>Regards,<br/>R&amp;D<br/>Attendance Monitoring Team</p>
        </body></html>
        """

    @staticmethod
    def build_early_logout_email(context: Dict[str, Any]) -> str:
        employee_name = _safe_text(context.get("employee_name") or "Employee")
        attendance_date = context.get("attendance_date") or datetime.now().date().isoformat()
        record = context.get("record") or {}
        classification = context.get("classification") or AttendanceShiftEngine.classify_record(record)
        assignment = context.get("assignment") or EmailReportsService._resolve_assignment(record)
        shift_context = EmailReportsService._resolve_shift_timings(record, assignment, classification)
        shift_name = shift_context["shift_name"]
        login_cutoff = _safe_text(shift_context["login_cutoff"])
        logout_cutoff = _safe_text(shift_context["logout_cutoff"])
        shift_timing = f"Login by {login_cutoff}, Logout by {logout_cutoff}"
        expected_logout = logout_cutoff
        actual_logout = _format_time(record.get("last_punch"))
        login_deviations = int(context.get("login_deviations") or 0)
        logout_deviations = int(context.get("logout_deviations") or 0)
        escalations = int(context.get("escalations") or (login_deviations + logout_deviations) // 3)

        return f"""
        <html><body style=\"font-family:Arial,Helvetica,sans-serif;color:#111827;line-height:1.5;\">
          <p>Dear {html.escape(employee_name)},</p>
          <p>This email is regarding your attendance on {html.escape(str(attendance_date))}. Our records indicate that you logged out earlier than the required logout time for this shift.</p>
          <h3 style=\"margin-bottom:8px;\">Attendance Details</h3>
          <table cellpadding=\"6\" cellspacing=\"0\" style=\"border-collapse:collapse;\">
            <tr><td><strong>Employee Name</strong></td><td>{html.escape(employee_name)}</td></tr>
            <tr><td><strong>Attendance Date</strong></td><td>{html.escape(str(attendance_date))}</td></tr>
            <tr><td><strong>Assigned Shift</strong></td><td>{html.escape(shift_name)}</td></tr>
            <tr><td><strong>Shift Timing</strong></td><td>{html.escape(shift_timing)}</td></tr>
            <tr><td><strong>Expected Logout Time</strong></td><td>{html.escape(expected_logout)}</td></tr>
            <tr><td><strong>Actual Logout Time</strong></td><td>{html.escape(actual_logout)}</td></tr>
          </table>
          <h3 style=\"margin-top:16px;\">Observation</h3>
          <p>As per your assigned shift schedule, your minimum required logout time was <strong>{html.escape(expected_logout)}</strong>.</p>
          <p>However, your attendance record shows that you logged out at <strong>{html.escape(actual_logout)}</strong>, which has resulted in a Logout Deviation.</p>
          <h3 style=\"margin-top:16px;\">Deviation Summary</h3>
          <table cellpadding=\"6\" cellspacing=\"0\" style=\"border-collapse:collapse;\">
            <tr><td><strong>Logout Deviation Added</strong></td><td>1</td></tr>
            <tr><td><strong>Current Total Login Deviations</strong></td><td>{login_deviations}</td></tr>
            <tr><td><strong>Current Total Logout Deviations</strong></td><td>{logout_deviations}</td></tr>
            <tr><td><strong>Current Escalations</strong></td><td>{escalations}</td></tr>
          </table>
          <p style=\"margin-top:12px;\"><strong>Attendance Policy</strong></p>
          <ul>
            <li>1 Late Login = 1 Login Deviation</li>
            <li>1 Early Logout = 1 Logout Deviation</li>
            <li>Every 3 Deviations = 1 Escalation</li>
            <li>Every 3 Escalations = ₹1000 Fine</li>
          </ul>
          <p>Kindly ensure that you complete your assigned shift hours and avoid further attendance deviations.</p>
          <p>Please reply to this email if you believe there is any discrepancy in the attendance record.</p>
          <p>Regards,<br/>R&amp;D<br/>Attendance Monitoring Team</p>
        </body></html>
        """

    @staticmethod
    def build_monthly_attendance_email(context: Dict[str, Any]) -> str:
        employee_id = str(context.get("employee_id") or "")
        employee_name = _safe_text(context.get("employee_name") or "Employee")
        month = int(context.get("month") or _previous_completed_month()[0])
        year = int(context.get("year") or _previous_completed_month()[1])
        month_label = datetime(year, month, 1).strftime("%B %Y")
        detail = analytics_service.get_employee_detail(employee_id, month=month, year=year)
        summary = analytics_service.get_employee_monthly_attendance(employee_id, month=month, year=year)
        rows = detail.get("records", []) or []
        employee_code = _safe_text(detail.get("employee_code") or context.get("employee_code") or employee_id)

        shift_name = "Assigned Shift"
        shift_timing = "Shift schedule will be applied from the employee assignment"
        if rows:
            first_record = rows[0]
            assignment = EmailReportsService._resolve_assignment({
                "employee_id": employee_id,
                "employee_name": employee_name,
                "attendance_date": first_record.get("date") or f"{year:04d}-{month:02d}-01",
            })
            shift_context = EmailReportsService._resolve_shift_timings({"shift_type": assignment.get("shift_type"), "shift_name": assignment.get("shift_name")}, assignment)
            shift_name = str(shift_context["shift_name"] or shift_name)
            shift_timing = f"Login by {shift_context['login_cutoff']}, Logout by {shift_context['logout_cutoff']}"

        working_days = int(summary.get("present_days") or 0)
        login_deviations = int(summary.get("login_deviation") or 0)
        logout_deviations = int(summary.get("logout_deviation") or 0)
        total_deviations = int(summary.get("total_deviations") or (login_deviations + logout_deviations))
        escalations = int(summary.get("escalations") or total_deviations // 3)
        fine_amount = escalations * 1000

        table_rows = "".join(
            f"<tr><td style='border:1px solid #d1d5db;padding:6px;'>{html.escape(str(item.get('date') or ''))}</td>"
            f"<td style='border:1px solid #d1d5db;padding:6px;'>{html.escape(str(item.get('weekday') or ''))}</td>"
            f"<td style='border:1px solid #d1d5db;padding:6px;'>{html.escape(str(item.get('first_punch') or ''))}</td>"
            f"<td style='border:1px solid #d1d5db;padding:6px;'>{html.escape(str(item.get('last_punch') or ''))}</td>"
            f"<td style='border:1px solid #d1d5db;padding:6px;'>{html.escape(str(item.get('total_time') or '0'))}</td>"
            f"<td style='border:1px solid #d1d5db;padding:6px;'>{html.escape(str(item.get('status') or ''))}</td>"
            f"<td style='border:1px solid #d1d5db;padding:6px;'>{'Yes' if item.get('is_late') else 'No'}</td>"
            f"<td style='border:1px solid #d1d5db;padding:6px;'>{'Yes' if item.get('is_early_out') else 'No'}</td>"
            f"<td style='border:1px solid #d1d5db;padding:6px;'>{'Yes' if item.get('is_missing_punch') else 'No'}</td></tr>"
            for item in rows
        )

        return f"""
        <html><body style=\"font-family:Arial,Helvetica,sans-serif;color:#111827;line-height:1.5;\">
          <p>Dear {html.escape(employee_name)},</p>
          <p>I have completed the attendance analysis for <strong>{html.escape(month_label)}</strong>.</p>
          <h3 style=\"margin-bottom:8px;\">Employee Details</h3>
          <table cellpadding=\"6\" cellspacing=\"0\" style=\"border-collapse:collapse;\">
            <tr><td><strong>Employee Name</strong></td><td>{html.escape(employee_name)}</td></tr>
            <tr><td><strong>Employee ID</strong></td><td>{html.escape(employee_code)}</td></tr>
            <tr><td><strong>Assigned Shift</strong></td><td>{html.escape(shift_name)}</td></tr>
            <tr><td><strong>Shift Timing</strong></td><td>{html.escape(shift_timing)}</td></tr>
          </table>
          <h3 style=\"margin-top:16px;\">Attendance Summary</h3>
          <table cellpadding=\"6\" cellspacing=\"0\" style=\"border-collapse:collapse;\">
            <tr><td style='border:1px solid #d1d5db;padding:6px;'><strong>Total Working Days Attended</strong></td><td style='border:1px solid #d1d5db;padding:6px;'>{working_days}</td></tr>
            <tr><td style='border:1px solid #d1d5db;padding:6px;'><strong>Total Login Deviations</strong></td><td style='border:1px solid #d1d5db;padding:6px;'>{login_deviations}</td></tr>
            <tr><td style='border:1px solid #d1d5db;padding:6px;'><strong>Total Logout Deviations</strong></td><td style='border:1px solid #d1d5db;padding:6px;'>{logout_deviations}</td></tr>
            <tr><td style='border:1px solid #d1d5db;padding:6px;'><strong>Total Deviations</strong></td><td style='border:1px solid #d1d5db;padding:6px;'>{total_deviations}</td></tr>
            <tr><td style='border:1px solid #d1d5db;padding:6px;'><strong>Applicable Escalations</strong></td><td style='border:1px solid #d1d5db;padding:6px;'>{escalations}</td></tr>
            <tr><td style='border:1px solid #d1d5db;padding:6px;'><strong>Fine Applicable</strong></td><td style='border:1px solid #d1d5db;padding:6px;'>₹{fine_amount}</td></tr>
          </table>
          <p style=\"margin-top:14px;\">Attendance records for the selected month are listed below.</p>
          <table cellpadding=\"6\" cellspacing=\"0\" style=\"border-collapse:collapse;width:100%;\">
            <thead><tr style='background:#f3f4f6;'><th style='border:1px solid #d1d5db;padding:6px;text-align:left;'>Date</th><th style='border:1px solid #d1d5db;padding:6px;text-align:left;'>Weekday</th><th style='border:1px solid #d1d5db;padding:6px;text-align:left;'>First Punch</th><th style='border:1px solid #d1d5db;padding:6px;text-align:left;'>Last Punch</th><th style='border:1px solid #d1d5db;padding:6px;text-align:left;'>Hours</th><th style='border:1px solid #d1d5db;padding:6px;text-align:left;'>Status</th><th style='border:1px solid #d1d5db;padding:6px;text-align:left;'>Is Late</th><th style='border:1px solid #d1d5db;padding:6px;text-align:left;'>Is Early Out</th><th style='border:1px solid #d1d5db;padding:6px;text-align:left;'>Is Missing Punch</th></tr></thead>
            <tbody>{table_rows}</tbody>
          </table>
          <p style=\"margin-top:14px;\">The attendance data is sourced directly from the attendance vendor system and evaluated according to company attendance policy.</p>
          <p>Regards,<br/>R&amp;D<br/>Attendance Monitoring Team</p>
        </body></html>
        """

    @staticmethod
    def _build_csv_attachment(employee_id: str, month: int | None = None, year: int | None = None) -> tuple[str, bytes]:
        detail = analytics_service.get_employee_detail(employee_id, month=month, year=year)
        rows = detail.get("records", []) or []

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Employee Name", "Employee ID", "Date", "Weekday", "First Punch", "Last Punch", "Hours", "Status", "Is Late", "Is Early Out", "Is Missing Punch"])
        for row in rows:
            writer.writerow([
                detail.get("employee_name") or "Employee",
                detail.get("employee_code") or employee_id,
                row.get("date") or "",
                row.get("weekday") or "",
                row.get("first_punch") or "",
                row.get("last_punch") or "",
                row.get("total_time") or 0,
                row.get("status") or "",
                "Yes" if row.get("is_late") else "No",
                "Yes" if row.get("is_early_out") else "No",
                "Yes" if row.get("is_missing_punch") else "No",
            ])
        effective_month = month or _previous_completed_month()[0]
        effective_year = year or _previous_completed_month()[1]
        filename = f"attendance-{detail.get('employee_code') or employee_id}-{effective_month:02d}-{effective_year}.csv"
        return filename, output.getvalue().encode("utf-8")

    @staticmethod
    def _body_for(employee_name: str, email_type: str, context: Dict[str, Any] | None = None) -> str:
        normalized = str(email_type or "").lower()
        context = context or {}
        if normalized == "late_login_alert":
            return EmailReportsService.build_late_login_email(context)
        if normalized == "early_logout_alert":
            return EmailReportsService.build_early_logout_email(context)
        if normalized == "monthly_report":
            return EmailReportsService.build_monthly_attendance_email(context)
        label = normalized.replace("_", " ")
        return f"<p>Hello {html.escape(employee_name or 'Employee')},</p><p>This is your automated {html.escape(label)} notification from the Attendance Dashboard.</p>"

    def send_email(self, recipient_email: str, subject: str, email_body: str, email_type: str, employee_name: str, cc_recipients: list[str] | None = None, attachments: list[dict[str, Any]] | None = None) -> str:
        api_key = (getattr(settings, "RESEND_API_KEY", None) or os.getenv("RESEND_API_KEY") or "").strip()
        from_email = (getattr(settings, "RESEND_FROM_EMAIL", None) or os.getenv("RESEND_FROM_EMAIL") or "").strip()

        if not api_key or not from_email:
            raise RuntimeError("Resend is not configured. Set RESEND_API_KEY and RESEND_FROM_EMAIL.")

        payload = {
            "from": from_email,
            "to": [recipient_email],
            "subject": subject or self._subject_for(email_type),
            "html": email_body,
            "text": email_body,
        }
        if cc_recipients:
            payload["cc"] = [email for email in cc_recipients if email]
        if attachments:
            payload["attachments"] = attachments

        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        body_text = (response.text or "").strip()
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"Resend delivery failed: status={response.status_code}, body={body_text[:500]}")

        try:
            data = response.json() if body_text else {}
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Resend returned an invalid response body") from exc

        message_id = str(data.get("id") or data.get("message_id") or "").strip()
        if not message_id:
            raise RuntimeError("Resend returned no provider message ID")
        return message_id

    @staticmethod
    def _safe_json(response: httpx.Response, action: str, fallback: Any = None) -> Any:
        body_text = (response.text or "").strip()
        if response.status_code in (200, 201, 204):
            if response.status_code == 204 or not body_text:
                return fallback
            try:
                return response.json()
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Supabase returned non-JSON response for {action}: status={response.status_code}, body={body_text[:500]}") from exc

        raise RuntimeError(f"Supabase request failed for {action}: status={response.status_code}, body={body_text[:500]}")

    def list_logs(self) -> list[Dict[str, Any]]:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                self._table_url(),
                headers=SUPABASE_HEADERS_SERVICE,
                params={"select": "*", "order": "sent_at.desc"},
            )

        rows = self._safe_json(response, action="list_logs", fallback=[])
        return rows if isinstance(rows, list) else []

    def log_activity(
        self,
        employee_id: str,
        employee_name: str,
        recipient_email: str,
        email_type: str,
        status: str = "SENT",
        provider: str = "resend",
        provider_message_id: str | None = None,
        skip_send: bool = False,
        context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        normalized_status = str(status or "sent").strip().lower()
        if normalized_status not in {"sent", "failed", "pending"}:
            normalized_status = "sent"

        failure_error: Exception | None = None
        context = dict(context or {})
        attendance_date = context.get("attendance_date") or None
        record = context.get("record")
        if not record and str(employee_id).strip() and attendance_date:
            fetched = attendance_service.get_all_attendance(limit=1, employee_id=str(employee_id), start_date=str(attendance_date), end_date=str(attendance_date))
            records = fetched.get("records") if isinstance(fetched, dict) else None
            if isinstance(records, list) and records:
                record = records[0]
        classification = context.get("classification") or (AttendanceShiftEngine.classify_record(record) if record else {})
        if record and not context.get("assignment"):
            context["assignment"] = EmailReportsService._resolve_assignment(record)
        if record and not context.get("classification"):
            context["classification"] = classification
        if record and not context.get("record"):
            context["record"] = record
        if str(email_type).lower() == "monthly_report":
            context["month"] = context.get("month") or _previous_completed_month()[0]
            context["year"] = context.get("year") or _previous_completed_month()[1]
        elif not context.get("month") and isinstance(attendance_date, str) and len(attendance_date) >= 7 and attendance_date[4] == "-":
            context["month"] = int(attendance_date[5:7])
            context["year"] = int(attendance_date[:4])
        subject = self._subject_for(email_type, context)
        email_body = self._body_for(employee_name, email_type, context)

        try:
            if not skip_send:
                attachments = None
                ceo_email = self._fetch_ceo_email()
                cc_recipients = [ceo_email] if ceo_email else None
                if str(email_type).lower() == "monthly_report":
                    filename, csv_bytes = self._build_csv_attachment(str(context.get("employee_id") or employee_id), month=context.get("month"), year=context.get("year"))
                    attachments = [{"filename": filename, "content": base64.b64encode(csv_bytes).decode("ascii")}]
                try:
                    provider_message_id = self.send_email(
                        recipient_email=str(recipient_email),
                        subject=subject,
                        email_body=email_body,
                        email_type=email_type,
                        employee_name=employee_name,
                        cc_recipients=cc_recipients,
                        attachments=attachments,
                    )
                except TypeError as exc:
                    if "unexpected keyword argument" not in str(exc):
                        raise
                    provider_message_id = self.send_email(
                        recipient_email=str(recipient_email),
                        subject=subject,
                        email_body=email_body,
                        email_type=email_type,
                        employee_name=employee_name,
                    )
            normalized_status = "sent" if provider_message_id or normalized_status == "sent" else normalized_status
        except Exception as exc:
            failure_error = exc
            normalized_status = "failed"
            logger.exception("Resend email delivery failed for %s", recipient_email)

        payload = {
            "employee_id": employee_id,
            "employee_name": employee_name,
            "employee_email": recipient_email or None,
            "cc_email": None,
            "email_type": email_type,
            "subject": subject,
            "email_body": email_body,
            "status": normalized_status,
            "provider": provider,
            "provider_message_id": provider_message_id,
            "sent_at": "now()",
        }

        with httpx.Client(timeout=10.0) as client:
            response = client.post(self._table_url(), headers=SUPABASE_HEADERS_SERVICE, json=payload)

        rows = self._safe_json(response, action="log_activity", fallback=[])
        result = rows[0] if isinstance(rows, list) and rows else rows

        if failure_error is not None:
            raise RuntimeError(f"Resend email delivery failed: {failure_error}") from failure_error

        return result


email_reports_service = EmailReportsService()
