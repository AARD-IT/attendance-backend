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
    "late_login_enabled": False,
    "late_login_delay": "same_day",
    "late_login_time": "18:00",
    "early_logout_enabled": False,
    "early_logout_delay": "same_day",
    "early_logout_time": "22:30",
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


automation_settings_service = AutomationSettingsService()
