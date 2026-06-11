import json
import logging
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SUPABASE_HEADERS_SERVICE = {
    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}


class EmailPreferencesService:
    def _table_url(self) -> str:
        return f"{settings.SUPABASE_URL}/rest/v1/email_preferences"

    def _log_response(self, action: str, response: httpx.Response) -> None:
        request_url = str(response.request.url) if response.request else self._table_url()
        body_preview = (response.text or "").strip()[:500]
        logger.warning(
            "Supabase email_preferences %s | url=%s | status=%s | body=%s",
            action,
            request_url,
            response.status_code,
            body_preview,
        )

    def _safe_json(self, response: httpx.Response, action: str, fallback: Any = None) -> Any:
        self._log_response(action, response)

        body_text = (response.text or "").strip()
        if response.status_code in (200, 201, 204):
            if response.status_code == 204 or not body_text:
                return fallback
            try:
                return response.json()
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"Supabase returned non-JSON response for {action}: "
                    f"status={response.status_code}, body={body_text[:500]}"
                ) from exc

        raise RuntimeError(
            f"Supabase request failed for {action}: status={response.status_code}, body={body_text[:500]}"
        )

    def list_preferences(self) -> list[Dict[str, Any]]:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(self._table_url(), headers=SUPABASE_HEADERS_SERVICE)

        return self._safe_json(response, action="list_preferences", fallback=[])

    def get_preference(self, employee_id: str) -> Optional[Dict[str, Any]]:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                self._table_url(),
                headers=SUPABASE_HEADERS_SERVICE,
                params={"employee_id": f"eq.{employee_id}", "select": "*"},
            )

        rows = self._safe_json(response, action="get_preference", fallback=[])
        if isinstance(rows, list) and len(rows) > 1:
            logger.warning("Duplicate email preference rows found for employee_id=%s; returning first record", employee_id)
        return rows[0] if isinstance(rows, list) and rows else None

    def ensure_preference(self, employee_id: str, employee_name: str, employee_email: str) -> Dict[str, Any]:
        existing = self.get_preference(employee_id)
        if existing:
            payload = {
                "employee_name": existing.get("employee_name") or employee_name,
                "employee_email": employee_email or existing.get("employee_email"),
                "updated_at": "now()",
            }
            with httpx.Client(timeout=10.0) as client:
                response = client.patch(
                    f"{self._table_url()}?employee_id=eq.{employee_id}",
                    headers=SUPABASE_HEADERS_SERVICE,
                    json=payload,
                )
            rows = self._safe_json(response, action="ensure_preference_refresh", fallback=[])
            return rows[0] if isinstance(rows, list) and rows else {**existing, **payload}

        payload = {
            "employee_id": employee_id,
            "employee_name": employee_name,
            "employee_email": employee_email,
            "monthly_report_mode": "manual",
            "late_login_mode": "manual",
            "early_logout_mode": "manual",
        }

        with httpx.Client(timeout=10.0) as client:
            response = client.post(self._table_url(), headers=SUPABASE_HEADERS_SERVICE, json=payload)

        if response.status_code == 409:
            existing = self.get_preference(employee_id)
            if existing:
                return existing

        rows = self._safe_json(response, action="ensure_preference", fallback=[])
        return rows[0] if isinstance(rows, list) and rows else rows

    def update_preference(self, employee_id: str, mode_type: str, mode_value: str) -> Dict[str, Any]:
        existing = self.get_preference(employee_id)
        if not existing:
            raise ValueError("Preference record not found")

        payload = {mode_type: mode_value, "updated_at": "now()"}
        with httpx.Client(timeout=10.0) as client:
            response = client.patch(
                f"{self._table_url()}?employee_id=eq.{employee_id}",
                headers=SUPABASE_HEADERS_SERVICE,
                json=payload,
            )

        rows = self._safe_json(response, action="update_preference", fallback=[])
        return rows[0] if isinstance(rows, list) and rows else existing


email_preferences_service = EmailPreferencesService()
