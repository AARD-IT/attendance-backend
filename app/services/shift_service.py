"""CRUD service for dynamic shift master configuration."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

SUPABASE_BASE = settings.SUPABASE_URL.rstrip("/")
SUPABASE_HEADERS = {
    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

DEFAULT_SHIFT_SEEDS = [
    {
        "shift_name": "Shift 1",
        "start_time": "10:20:00",
        "end_time": "18:00:00",
        "grace_time_minutes": 15,
        "minimum_working_hours": 8,
        "login_deviation_minutes": 15,
        "logout_deviation_minutes": 0,
        "status": True,
    },
    {
        "shift_name": "Shift 2",
        "start_time": "14:20:00",
        "end_time": "22:00:00",
        "grace_time_minutes": 15,
        "minimum_working_hours": 8,
        "login_deviation_minutes": 15,
        "logout_deviation_minutes": 0,
        "status": True,
    },
]


class ShiftService:
    _cache: List[Dict[str, Any]] | None = None
    _cache_at: datetime | None = None
    _cache_ttl_seconds = 60

    @staticmethod
    def _request(method: str, *, params: str = "", json_body: Dict[str, Any] | None = None) -> httpx.Response:
        url = f"{SUPABASE_BASE}/rest/v1/shifts{params}"
        headers = {**SUPABASE_HEADERS}
        if json_body is not None:
            headers["Prefer"] = "return=representation"
        try:
            with httpx.Client(timeout=10.0) as client:
                if method == "GET":
                    return client.get(url, headers=headers)
                if method == "POST":
                    return client.post(url, json=json_body, headers=headers)
                if method == "DELETE":
                    return client.delete(url, headers=headers)
                return client.patch(url, json=json_body, headers=headers)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Supabase request failed") from exc

    @classmethod
    def _invalidate_cache(cls) -> None:
        cls._cache = None
        cls._cache_at = None

    @classmethod
    def _fallback_shifts(cls) -> List[Dict[str, Any]]:
        return [{**item, "id": item["shift_name"], "_fallback": True} for item in DEFAULT_SHIFT_SEEDS]

    @staticmethod
    def _is_uuid(value: str) -> bool:
        return bool(UUID_PATTERN.match(str(value or "").strip()))

    @classmethod
    def _fetch_from_db(cls, *, force: bool = False) -> Tuple[List[Dict[str, Any]], bool]:
        response = cls._request("GET", params="?select=*&order=shift_name.asc")
        if response.status_code == 404:
            return [], False
        if response.status_code != 200:
            return [], False
        rows = response.json() or []
        return (rows if isinstance(rows, list) else []), True

    @classmethod
    def _ensure_seeded_shifts(cls) -> List[Dict[str, Any]]:
        rows, table_exists = cls._fetch_from_db(force=True)
        if rows:
            return rows
        if not table_exists:
            return cls._fallback_shifts()

        for seed in DEFAULT_SHIFT_SEEDS:
            body = {**seed, "updated_at": datetime.utcnow().isoformat()}
            response = cls._request("POST", json_body=body)
            if response.status_code not in (200, 201, 409):
                continue

        rows, _ = cls._fetch_from_db(force=True)
        return rows if rows else cls._fallback_shifts()

    @classmethod
    def _resolve_shift(cls, shift_id: str) -> Optional[Dict[str, Any]]:
        identifier = str(shift_id or "").strip()
        if not identifier:
            return None

        rows = cls.list_shifts()

        if cls._is_uuid(identifier):
            for row in rows:
                if str(row.get("id")) == identifier:
                    return row

        normalized = " ".join(identifier.lower().split())
        for row in rows:
            row_name = " ".join(str(row.get("shift_name") or "").strip().lower().split())
            if row_name == normalized or str(row.get("id")) == identifier:
                return row

        if normalized in {"1", "one", "shift 1"}:
            return cls._resolve_shift("Shift 1")
        if normalized in {"2", "two", "shift 2"}:
            return cls._resolve_shift("Shift 2")
        return None

    @classmethod
    def _patch_filter(cls, shift: Dict[str, Any]) -> str:
        shift_id = str(shift.get("id") or "")
        if cls._is_uuid(shift_id):
            return f"?id=eq.{quote(shift_id, safe='')}"
        shift_name = str(shift.get("shift_name") or "")
        return f"?shift_name=eq.{quote(shift_name, safe='')}"

    @classmethod
    def list_shifts(cls, *, active_only: bool = False, force_refresh: bool = False) -> List[Dict[str, Any]]:
        now = datetime.utcnow()
        if (
            not force_refresh
            and cls._cache is not None
            and cls._cache_at is not None
            and (now - cls._cache_at).total_seconds() < cls._cache_ttl_seconds
        ):
            rows = cls._cache
        else:
            rows, table_exists = cls._fetch_from_db()
            if not rows and table_exists:
                rows = cls._ensure_seeded_shifts()
            elif not rows:
                rows = cls._fallback_shifts()
            cls._cache = rows
            cls._cache_at = now

        if active_only:
            return [row for row in rows if row.get("status", True)]
        return rows

    @classmethod
    def get_shift(cls, shift_id: str) -> Optional[Dict[str, Any]]:
        return cls._resolve_shift(shift_id)

    @classmethod
    def get_shift_by_name(cls, shift_name: str) -> Optional[Dict[str, Any]]:
        normalized = " ".join(str(shift_name or "").strip().lower().split())
        for row in cls.list_shifts():
            row_name = " ".join(str(row.get("shift_name") or "").strip().lower().split())
            if row_name == normalized:
                return row
        if normalized in {"1", "one", "shift 1"}:
            return cls.get_shift_by_name("Shift 1")
        if normalized in {"2", "two", "shift 2"}:
            return cls.get_shift_by_name("Shift 2")
        return None

    @classmethod
    def get_default_shift(cls) -> Dict[str, Any]:
        active = cls.list_shifts(active_only=True)
        if active:
            return active[0]
        rows = cls.list_shifts()
        return rows[0] if rows else cls._fallback_shifts()[0]

    @staticmethod
    def _normalize_time(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="Shift time is required")
        if len(text) == 5:
            return f"{text}:00"
        return text

    @classmethod
    def create_shift(cls, payload: Dict[str, Any], created_by: str | None = None) -> Dict[str, Any]:
        body = {
            "shift_name": str(payload.get("shift_name") or "").strip(),
            "start_time": cls._normalize_time(payload.get("start_time")),
            "end_time": cls._normalize_time(payload.get("end_time")),
            "grace_time_minutes": int(payload.get("grace_time_minutes", 15)),
            "minimum_working_hours": float(payload.get("minimum_working_hours", 8)),
            "login_deviation_minutes": int(payload.get("login_deviation_minutes", 15)),
            "logout_deviation_minutes": int(payload.get("logout_deviation_minutes", 30)),
            "status": bool(payload.get("status", True)),
            "created_by": created_by,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if not body["shift_name"]:
            raise HTTPException(status_code=400, detail="shift_name is required")

        response = cls._request("POST", json_body=body)
        if response.status_code not in (200, 201):
            detail = (response.text or "").strip()[:500]
            if response.status_code == 404:
                raise HTTPException(
                    status_code=503,
                    detail="Shifts table not found. Apply migration backend/sql/015_dynamic_shifts_and_notifications.sql",
                )
            raise HTTPException(status_code=500, detail=f"Failed to create shift: {detail or response.status_code}")
        cls._invalidate_cache()
        result = response.json()
        return result[0] if isinstance(result, list) else result

    @classmethod
    def update_shift(cls, shift_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        existing = cls._resolve_shift(shift_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Shift not found")

        if existing.get("_fallback") or not cls._is_uuid(str(existing.get("id") or "")):
            cls._ensure_seeded_shifts()
            existing = cls._resolve_shift(str(existing.get("shift_name") or shift_id))
            if not existing:
                raise HTTPException(status_code=404, detail="Shift not found")

        body: Dict[str, Any] = {"updated_at": datetime.utcnow().isoformat()}
        for field in (
            "shift_name",
            "grace_time_minutes",
            "minimum_working_hours",
            "login_deviation_minutes",
            "logout_deviation_minutes",
            "status",
        ):
            if field in payload:
                body[field] = payload[field]
        if "start_time" in payload:
            body["start_time"] = cls._normalize_time(payload["start_time"])
        if "end_time" in payload:
            body["end_time"] = cls._normalize_time(payload["end_time"])

        response = cls._request("PATCH", params=cls._patch_filter(existing), json_body=body)
        if response.status_code not in (200, 204):
            detail = (response.text or "").strip()[:500]
            if response.status_code == 404:
                raise HTTPException(
                    status_code=503,
                    detail="Shifts table not found. Apply migration backend/sql/015_dynamic_shifts_and_notifications.sql",
                )
            raise HTTPException(status_code=500, detail=f"Failed to update shift: {detail or response.status_code}")
        cls._invalidate_cache()
        result = response.json()
        return result[0] if isinstance(result, list) and result else {**existing, **body}

    @classmethod
    def delete_shift(cls, shift_id: str) -> bool:
        existing = cls._resolve_shift(shift_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Shift not found")
        if existing.get("_fallback") or not cls._is_uuid(str(existing.get("id") or "")):
            cls._ensure_seeded_shifts()
            existing = cls._resolve_shift(str(existing.get("shift_name") or shift_id))
            if not existing:
                raise HTTPException(status_code=404, detail="Shift not found")

        response = cls._request("DELETE", params=cls._patch_filter(existing))
        if response.status_code not in (200, 204):
            detail = (response.text or "").strip()[:500]
            raise HTTPException(status_code=500, detail=f"Failed to delete shift: {detail or response.status_code}")
        cls._invalidate_cache()
        return True


shift_service = ShiftService()
