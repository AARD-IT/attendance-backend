import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SUPABASE_HEADERS_SERVICE = {
    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}


class AutomationJobLogService:
    @staticmethod
    def _table_url() -> str:
        return f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/automation_job_executions"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _safe_json(response: httpx.Response, fallback: Any = None) -> Any:
        if response.status_code in (200, 201, 204):
            text = (response.text or "").strip()
            if response.status_code == 204 or not text:
                return fallback
            try:
                return response.json()
            except (TypeError, ValueError, json.JSONDecodeError):
                return fallback
        logger.warning("automation job log request failed status=%s body=%s", response.status_code, (response.text or "")[:500])
        return fallback

    def claim_job(self, job_type: str, execution_date: str) -> Dict[str, Any] | None:
        payload = {
            "job_type": job_type,
            "execution_date": execution_date,
            "last_run_at": self._now_iso(),
            "status": "RUNNING",
        }
        params = {"on_conflict": "job_type,execution_date"}
        headers = {**SUPABASE_HEADERS_SERVICE, "Prefer": "resolution=ignore-duplicates,return=representation"}
        with httpx.Client(timeout=10.0) as client:
            response = client.post(self._table_url(), headers=headers, params=params, json=payload)

        rows = self._safe_json(response, fallback=[])
        if isinstance(rows, list) and rows:
            return rows[0]
        if isinstance(rows, dict) and rows:
            return rows
        return None

    def finalize_job(self, job_type: str, execution_date: str, status: str, details: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
        payload = {
            "status": status,
            "last_run_at": self._now_iso(),
        }
        if details is not None:
            payload["details"] = details

        with httpx.Client(timeout=10.0) as client:
            response = client.patch(
                self._table_url(),
                headers={**SUPABASE_HEADERS_SERVICE, "Prefer": "return=representation"},
                params={"job_type": f"eq.{job_type}", "execution_date": f"eq.{execution_date}"},
                json=payload,
            )

        rows = self._safe_json(response, fallback=[])
        if isinstance(rows, list) and rows:
            return rows[0]
        if isinstance(rows, dict):
            return rows
        return None


automation_job_log_service = AutomationJobLogService()