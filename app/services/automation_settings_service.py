import logging
from typing import Any, Dict

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SUPABASE_HEADERS_SERVICE = {
    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}

DEFAULT_SETTINGS = {
    "monthly_report_enabled": False,
    "monthly_report_day": 5,
    "monthly_report_time": "09:00",
    "monthly_report_cc_enabled": False,
    "late_login_enabled": False,
    "late_login_delay": "same_day",
    "late_login_time": "18:00",
    "late_login_send_immediately": True,
    "late_login_delay_minutes": 0,
    "early_logout_enabled": False,
    "early_logout_delay": "same_day",
    "early_logout_time": "22:30",
    "early_logout_delay_minutes": 0,
    "missing_punch_enabled": False,
    "missing_punch_delay_minutes": 60,
    "escalation_enabled": False,
    "escalation_late_threshold": 5,
    "escalation_deviation_threshold": 5,
    "escalation_recipients": "",
}


class AutomationSettingsService:
    @staticmethod
    def _table_url() -> str:
        return f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/email_automation_settings"

    @staticmethod
    def _safe_json(response: httpx.Response, fallback: Any = None) -> Any:
        if response.status_code in (200, 201, 204):
            text = (response.text or "").strip()
            if response.status_code == 204 or not text:
                return fallback
            try:
                return response.json()
            except Exception:
                return fallback
        logger.warning("automation settings request failed with status=%s body=%s", response.status_code, (response.text or "")[:500])
        return fallback

    def get_settings(self) -> Dict[str, Any]:
        params = {"select": "*", "limit": "1"}
        with httpx.Client(timeout=10.0) as client:
            response = client.get(self._table_url(), headers=SUPABASE_HEADERS_SERVICE, params=params)
        rows = self._safe_json(response, fallback=[])
        if isinstance(rows, list) and rows:
            return {**DEFAULT_SETTINGS, **rows[0]}
        return dict(DEFAULT_SETTINGS)

    def upsert_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get_settings()
        body = {key: payload.get(key, current.get(key, DEFAULT_SETTINGS.get(key))) for key in DEFAULT_SETTINGS}
        for optional_key in (
            "monthly_report_template_id",
            "late_login_template_id",
            "early_logout_template_id",
            "missing_punch_template_id",
            "escalation_template_id",
        ):
            if optional_key in payload:
                body[optional_key] = payload[optional_key]

        if current.get("id"):
            with httpx.Client(timeout=10.0) as client:
                response = client.patch(
                    f"{self._table_url()}?id=eq.{current['id']}",
                    headers={**SUPABASE_HEADERS_SERVICE, "Prefer": "return=representation"},
                    json=body,
                )
        else:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(self._table_url(), headers={**SUPABASE_HEADERS_SERVICE, "Prefer": "return=representation"}, json=body)

        rows = self._safe_json(response, fallback=[])
        if isinstance(rows, list) and rows:
            return {**DEFAULT_SETTINGS, **rows[0]}
        return {**DEFAULT_SETTINGS, **current, **body}


automation_settings_service = AutomationSettingsService()
