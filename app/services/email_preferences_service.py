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

    def _enrich_preference_dynamically(self, pref: Dict[str, Any]) -> Dict[str, Any]:
        employee_id = pref.get("employee_id")
        if not employee_id:
            return pref
        try:
            from app.services.shift_assignment_service import shift_assignment_service
            assignments = shift_assignment_service.get_assignments(employee_id=employee_id, active_only=True)
            if assignments:
                assignment = assignments[0]
                pref["employee_name"] = str(assignment.get("employee_name") or pref.get("employee_name") or "").strip()
                pref["employee_email"] = str(assignment.get("employee_email") or "").strip()
                pref["cc_email"] = str(assignment.get("cc_email") or "").strip()
            else:
                from app.db.supabase import SupabaseClient
                profiles = SupabaseClient.get_all_profiles()
                profile = next((p for p in profiles if str(p.get("id")) == employee_id), None)
                if profile:
                    pref["employee_name"] = profile.get("full_name") or pref.get("employee_name")
                    pref["employee_email"] = profile.get("email") or pref.get("employee_email")
                    pref["cc_email"] = ""
        except Exception as exc:
            logger.warning("Failed to enrich preference dynamically: %s", exc)
        return pref

    def merge_duplicates(self, employee_id: str, rows: list[Dict[str, Any]]) -> Dict[str, Any]:
        logger.warning("Merging duplicate email preference rows for employee_id=%s", employee_id)
        # Sort rows to choose the best candidate as primary
        # Priority: has 'auto' modes, then latest updated_at
        def sort_key(r):
            auto_count = sum(1 for m in [r.get("monthly_report_mode"), r.get("late_login_mode"), r.get("early_logout_mode")] if m == "auto")
            return (auto_count, r.get("updated_at", ""))
        
        rows.sort(key=sort_key, reverse=True)
        primary = rows[0]
        duplicates = rows[1:]
        
        merged_modes = {
            "monthly_report_mode": primary.get("monthly_report_mode"),
            "late_login_mode": primary.get("late_login_mode"),
            "early_logout_mode": primary.get("early_logout_mode"),
        }
        for dup in duplicates:
            for mode in ["monthly_report_mode", "late_login_mode", "early_logout_mode"]:
                if dup.get(mode) == "auto":
                    merged_modes[mode] = "auto"
                    
        modes_changed = any(primary.get(m) != merged_modes[m] for m in merged_modes)
        if modes_changed:
            with httpx.Client(timeout=10.0) as client:
                client.patch(
                    f"{self._table_url()}?id=eq.{primary['id']}",
                    headers=SUPABASE_HEADERS_SERVICE,
                    json=merged_modes,
                )
            primary.update(merged_modes)
            
        for dup in duplicates:
            with httpx.Client(timeout=10.0) as client:
                client.delete(
                    f"{self._table_url()}?id=eq.{dup['id']}",
                    headers=SUPABASE_HEADERS_SERVICE,
                )
        return primary

    def list_preferences(self) -> list[Dict[str, Any]]:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(self._table_url(), headers=SUPABASE_HEADERS_SERVICE)

        raw_rows = self._safe_json(response, action="list_preferences", fallback=[])
        
        # Deduplicate and enrich dynamically
        unique_prefs = {}
        for r in raw_rows:
            emp_id = r.get("employee_id")
            if not emp_id:
                continue
            if emp_id in unique_prefs:
                unique_prefs[emp_id].append(r)
            else:
                unique_prefs[emp_id] = [r]
                
        deduped_rows = []
        for emp_id, group in unique_prefs.items():
            if len(group) > 1:
                primary = self.merge_duplicates(emp_id, group)
            else:
                primary = group[0]
            deduped_rows.append(self._enrich_preference_dynamically(primary))
            
        return deduped_rows

    def get_preference(self, employee_id: str) -> Optional[Dict[str, Any]]:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                self._table_url(),
                headers=SUPABASE_HEADERS_SERVICE,
                params={"employee_id": f"eq.{employee_id}", "select": "*"},
            )

        rows = self._safe_json(response, action="get_preference", fallback=[])
        if isinstance(rows, list) and len(rows) > 1:
            pref = self.merge_duplicates(employee_id, rows)
        else:
            pref = rows[0] if isinstance(rows, list) and rows else None
            
        if pref:
            pref = self._enrich_preference_dynamically(pref)
        return pref

    def ensure_preference(self, employee_id: str, employee_name: str, employee_email: str) -> Dict[str, Any]:
        existing = self.get_preference(employee_id)
        if existing:
            payload = {
                "employee_name": employee_name,
                "updated_at": "now()",
            }
            # Note: We do not save employee_email to email_preferences to keep shift management as single source of truth
            with httpx.Client(timeout=10.0) as client:
                response = client.patch(
                    f"{self._table_url()}?employee_id=eq.{employee_id}",
                    headers=SUPABASE_HEADERS_SERVICE,
                    json=payload,
                )
            rows = self._safe_json(response, action="ensure_preference_refresh", fallback=[])
            return self._enrich_preference_dynamically(rows[0] if isinstance(rows, list) and rows else {**existing, **payload})

        payload = {
            "employee_id": employee_id,
            "employee_name": employee_name,
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
        created = rows[0] if isinstance(rows, list) and rows else rows
        return self._enrich_preference_dynamically(created)

    def update_preference(self, employee_id: str, mode_type: str, mode_value: str) -> Dict[str, Any]:
        existing = self.get_preference(employee_id)
        if not existing:
            raise ValueError("Preference record not found")

        payload = {mode_type: mode_value, "updated_at": "now()"}
        with httpx.Client(timeout=10.0) as client:
            response = client.patch(
                f"{self._table_url()}?employee_id=eq.{employee_id}",
                headers={**SUPABASE_HEADERS_SERVICE, "Prefer": "return=representation"},
                json=payload,
            )

        rows = self._safe_json(response, action="update_preference", fallback=[])
        if isinstance(rows, list) and rows:
            updated = rows[0]
        else:
            # Supabase didn't return the row — construct it locally from existing + change
            updated = {**existing, mode_type: mode_value}
        return self._enrich_preference_dynamically(updated)


email_preferences_service = EmailPreferencesService()
