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
    "id": "global",
    "auto_refresh_enabled": False,
    "last_loaded_at": None,
    "last_loaded_by": None,
}


def _settings_id(user_id: str | None = None) -> str:
    return "global"


class CEODashboardSettingsService:
    @staticmethod
    def _table_url() -> str:
        return f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/ceo_dashboard_settings"

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
        logger.warning("ceo dashboard settings request failed with status=%s body=%s", response.status_code, (response.text or "")[:500])
        return fallback

    def get_settings(self, user_id: str | None = None) -> Dict[str, Any]:
        params = {"id": "eq.global", "select": "*", "limit": "1"}
        with httpx.Client(timeout=10.0) as client:
            response = client.get(self._table_url(), headers=SUPABASE_HEADERS_SERVICE, params=params)
        rows = self._safe_json(response, fallback=[])
        if isinstance(rows, list) and rows:
            return {**DEFAULT_SETTINGS, **rows[0]}
        return dict(DEFAULT_SETTINGS)

    def get_all_settings(self) -> list[Dict[str, Any]]:
        settings_row = self.get_settings()
        if settings_row:
            return [settings_row]
        return [dict(DEFAULT_SETTINGS)]

    def upsert_settings(self, payload: Dict[str, Any], user_id: str | None = None) -> Dict[str, Any]:
        body = {
            "id": "global",
            "auto_refresh_enabled": payload.get("auto_refresh_enabled", False),
            "last_loaded_at": payload.get("last_loaded_at"),
            "last_loaded_by": payload.get("last_loaded_by"),
        }
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                self._table_url(),
                headers={**SUPABASE_HEADERS_SERVICE, "Prefer": "resolution=merge-duplicates,return=representation"},
                json=body,
            )
        rows = self._safe_json(response, fallback=[])
        if isinstance(rows, list) and rows:
            return {**DEFAULT_SETTINGS, **rows[0]}
        return {**DEFAULT_SETTINGS, **body}

    def update_last_loaded(self, user_id: str, last_loaded_at: str | None, last_loaded_by: str | None = "auto") -> Dict[str, Any]:
        return self.upsert_settings(
            {
                "auto_refresh_enabled": True,
                "last_loaded_at": last_loaded_at,
                "last_loaded_by": last_loaded_by,
            }
        )


ceo_dashboard_settings_service = CEODashboardSettingsService()
