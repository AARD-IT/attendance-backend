"""Per-employee notification settings service."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SUPABASE_HEADERS = {
    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}

MODE_FIELDS = (
    "monthly_report_mode",
    "late_login_mode",
    "early_logout_mode",
    "missing_punch_mode",
    "escalation_mode",
)


def _normalize_mode(value: Any) -> str:
    text = str(value or "MANUAL").strip().upper()
    if text in {"AUTO", "AUTOMATIC"}:
        return "AUTOMATIC"
    return "MANUAL"


def _to_legacy_mode(value: Any) -> str:
    return "auto" if _normalize_mode(value) == "AUTOMATIC" else "manual"


class NotificationSettingsService:
    @staticmethod
    def _table_url() -> str:
        return f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/employee_notification_settings"

    @staticmethod
    def _legacy_table_url() -> str:
        return f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/email_preferences"

    def _safe_json(self, response: httpx.Response, fallback: Any = None) -> Any:
        if response.status_code in (200, 201, 204):
            text = (response.text or "").strip()
            if response.status_code == 204 or not text:
                return fallback
            try:
                return response.json()
            except Exception:
                return fallback
        return fallback

    def list_settings(self) -> List[Dict[str, Any]]:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(self._table_url(), headers=SUPABASE_HEADERS, params={"select": "*"})
        rows = self._safe_json(response, fallback=[])
        if isinstance(rows, list) and rows:
            return rows

        with httpx.Client(timeout=10.0) as client:
            legacy = client.get(self._legacy_table_url(), headers=SUPABASE_HEADERS, params={"select": "*"})
        legacy_rows = self._safe_json(legacy, fallback=[])
        if not isinstance(legacy_rows, list):
            return []
        return [self._from_legacy(row) for row in legacy_rows]

    def get_setting(self, employee_id: str) -> Optional[Dict[str, Any]]:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                self._table_url(),
                headers=SUPABASE_HEADERS,
                params={"employee_id": f"eq.{employee_id}", "select": "*"},
            )
        rows = self._safe_json(response, fallback=[])
        if isinstance(rows, list) and rows:
            return rows[0]

        with httpx.Client(timeout=10.0) as client:
            legacy = client.get(
                self._legacy_table_url(),
                headers=SUPABASE_HEADERS,
                params={"employee_id": f"eq.{employee_id}", "select": "*"},
            )
        legacy_rows = self._safe_json(legacy, fallback=[])
        return self._from_legacy(legacy_rows[0]) if isinstance(legacy_rows, list) and legacy_rows else None

    @staticmethod
    def _from_legacy(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row.get("id"),
            "employee_id": row.get("employee_id"),
            "employee_email": row.get("employee_email"),
            "cc_email": row.get("cc_email"),
            "monthly_report_mode": _normalize_mode(row.get("monthly_report_mode")),
            "late_login_mode": _normalize_mode(row.get("late_login_mode")),
            "early_logout_mode": _normalize_mode(row.get("early_logout_mode")),
            "missing_punch_mode": "MANUAL",
            "escalation_mode": "MANUAL",
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    def ensure_setting(self, employee_id: str, employee_name: str, employee_email: str, cc_email: str = "") -> Dict[str, Any]:
        existing = self.get_setting(employee_id)
        if existing:
            payload = {
                "employee_email": employee_email or existing.get("employee_email"),
                "cc_email": cc_email or existing.get("cc_email"),
                "updated_at": "now()",
            }
            with httpx.Client(timeout=10.0) as client:
                response = client.patch(
                    f"{self._table_url()}?employee_id=eq.{employee_id}",
                    headers={**SUPABASE_HEADERS, "Prefer": "return=representation"},
                    json=payload,
                )
            rows = self._safe_json(response, fallback=[])
            if isinstance(rows, list) and rows:
                return rows[0]
            return {**existing, **payload}

        payload = {
            "employee_id": employee_id,
            "employee_email": employee_email,
            "cc_email": cc_email,
            "monthly_report_mode": "MANUAL",
            "late_login_mode": "MANUAL",
            "early_logout_mode": "MANUAL",
            "missing_punch_mode": "MANUAL",
            "escalation_mode": "MANUAL",
        }
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                self._table_url(),
                headers={**SUPABASE_HEADERS, "Prefer": "return=representation"},
                json=payload,
            )
        rows = self._safe_json(response, fallback=[])
        if isinstance(rows, list) and rows:
            self._sync_legacy(rows[0], employee_name)
            return rows[0]
        return payload

    def update_settings(self, employee_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.get_setting(employee_id)
        if not existing:
            raise ValueError("Notification settings not found")

        body: Dict[str, Any] = {"updated_at": "now()"}
        for field in ("employee_email", "cc_email", *MODE_FIELDS):
            if field in payload:
                body[field] = _normalize_mode(payload[field]) if field.endswith("_mode") else payload[field]

        with httpx.Client(timeout=10.0) as client:
            response = client.patch(
                f"{self._table_url()}?employee_id=eq.{employee_id}",
                headers={**SUPABASE_HEADERS, "Prefer": "return=representation"},
                json=body,
            )
        rows = self._safe_json(response, fallback=[])
        updated = rows[0] if isinstance(rows, list) and rows else {**existing, **body}
        self._sync_legacy(updated, str(existing.get("employee_name") or payload.get("employee_name") or "Employee"))
        return updated

    def _sync_legacy(self, row: Dict[str, Any], employee_name: str) -> None:
        legacy_payload = {
            "employee_name": employee_name,
            "employee_email": row.get("employee_email"),
            "monthly_report_mode": _to_legacy_mode(row.get("monthly_report_mode")),
            "late_login_mode": _to_legacy_mode(row.get("late_login_mode")),
            "early_logout_mode": _to_legacy_mode(row.get("early_logout_mode")),
            "updated_at": "now()",
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                client.patch(
                    f"{self._legacy_table_url()}?employee_id=eq.{row.get('employee_id')}",
                    headers=SUPABASE_HEADERS,
                    json=legacy_payload,
                )
        except Exception as exc:
            logger.warning("Failed to sync legacy email preferences: %s", exc)


notification_settings_service = NotificationSettingsService()
