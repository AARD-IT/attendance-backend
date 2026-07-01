"""CRUD service for employee shift assignments with overlap validation and history."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.services.shift_service import shift_service

SUPABASE_BASE = settings.SUPABASE_URL.rstrip("/")
SUPABASE_HEADERS = {
    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}

PRIMARY_TABLE = "employee_shift_assignments"
LEGACY_TABLE = "shift_assignments"
HISTORY_TABLE = "shift_assignment_history"


class ShiftAssignmentService:
    @staticmethod
    def _request(table: str, method: str, *, json_body: Dict[str, Any] | None = None, params: str = "") -> httpx.Response:
        url = f"{SUPABASE_BASE}/rest/v1/{table}{params}"
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

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if not value:
            return None
        return datetime.fromisoformat(str(value)).date()

    @staticmethod
    def _assignment_window(assignment: Dict[str, Any]) -> tuple[date | None, date | None]:
        start = ShiftAssignmentService._parse_date(
            assignment.get("start_date") or assignment.get("effective_from")
        )
        end = ShiftAssignmentService._parse_date(
            assignment.get("end_date") or assignment.get("effective_to")
        )
        return start, end

    @staticmethod
    def _ranges_overlap(start_a: date, end_a: date, start_b: date, end_b: date) -> bool:
        return not (end_a < start_b or start_a > end_b)

    @classmethod
    def _resolve_shift_id(cls, payload: Dict[str, Any]) -> str | None:
        if payload.get("shift_id"):
            return str(payload["shift_id"])
        shift_type = payload.get("shift_type") or payload.get("shift_name")
        if shift_type:
            shift = shift_service.get_shift_by_name(str(shift_type))
            if shift:
                return str(shift.get("id"))
        return None

    @classmethod
    def _normalize_payload(cls, payload: Dict[str, Any], *, assigned_by: str | None = None) -> Dict[str, Any]:
        start_date = payload.get("start_date") or payload.get("effective_from")
        end_date = payload.get("end_date") or payload.get("effective_to")
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="start_date and end_date are required")

        start = cls._parse_date(start_date)
        end = cls._parse_date(end_date)
        if start is None or end is None or start > end:
            raise HTTPException(status_code=400, detail="Invalid date range")

        shift_id = cls._resolve_shift_id(payload)
        shift = shift_service.get_shift(shift_id) if shift_id else None
        shift_name = (shift or {}).get("shift_name") or payload.get("shift_type") or payload.get("shift_name") or shift_service.get_default_shift().get("shift_name")

        body = {
            "employee_id": str(payload.get("employee_id") or ""),
            "employee_name": payload.get("employee_name"),
            "employee_email": payload.get("employee_email"),
            "cc_email": payload.get("cc_email"),
            "shift_id": shift_id,
            "shift_type": shift_name,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "effective_from": start.isoformat(),
            "effective_to": end.isoformat(),
            "status": bool(payload.get("status", payload.get("is_active", True))),
            "is_active": bool(payload.get("status", payload.get("is_active", True))),
            "assigned_by": assigned_by or payload.get("assigned_by"),
            "updated_at": datetime.utcnow().isoformat(),
        }
        if payload.get("minerva_employee_id"):
            body["minerva_employee_id"] = payload.get("minerva_employee_id")
        if not body["employee_id"]:
            raise HTTPException(status_code=400, detail="employee_id is required")
        return body

    @classmethod
    def _validate_no_overlap(
        cls,
        employee_id: str,
        start: date,
        end: date,
        *,
        exclude_id: str | None = None,
    ) -> None:
        for assignment in cls.get_assignments(employee_id=employee_id):
            if exclude_id and str(assignment.get("id")) == str(exclude_id):
                continue
            active = assignment.get("status")
            if active is None:
                active = assignment.get("is_active", True)
            if active is False:
                continue
            other_start, other_end = cls._assignment_window(assignment)
            if other_start is None or other_end is None:
                continue
            if cls._ranges_overlap(start, end, other_start, other_end):
                raise HTTPException(
                    status_code=400,
                    detail="Employee already has an overlapping shift assignment for the selected date range",
                )

    @staticmethod
    def _enrich_assignment(row: Dict[str, Any]) -> Dict[str, Any]:
        enriched = dict(row)
        shift_id = enriched.get("shift_id")
        if shift_id:
            shift = shift_service.get_shift(str(shift_id))
            if shift:
                enriched["shift"] = shift
                enriched["shift_name"] = shift.get("shift_name")
                enriched["shift_type"] = shift.get("shift_name")
        else:
            shift_name = enriched.get("shift_type") or enriched.get("shift_name")
            if shift_name:
                shift = shift_service.get_shift_by_name(str(shift_name))
                if shift:
                    enriched["shift"] = shift
                    enriched["shift_name"] = shift.get("shift_name")
        enriched.setdefault("start_date", enriched.get("effective_from"))
        enriched.setdefault("end_date", enriched.get("effective_to"))
        enriched.setdefault("status", enriched.get("is_active", True))
        return enriched

    @classmethod
    def get_assignments(
        cls,
        *,
        employee_id: str | None = None,
        shift_id: str | None = None,
        active_only: bool = False,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        for table in (PRIMARY_TABLE, LEGACY_TABLE):
            params = "?select=*&order=created_at.desc"
            if employee_id:
                params += f"&employee_id=eq.{employee_id}"
            if shift_id:
                params += f"&shift_id=eq.{shift_id}"
            response = cls._request(table, "GET", params=params)
            if response.status_code == 200:
                payload = response.json()
                if isinstance(payload, list):
                    for item in payload:
                        item_id = str(item.get("id") or "")
                        if item_id and item_id in seen_ids:
                            continue
                        if item_id:
                            seen_ids.add(item_id)
                        results.append(cls._enrich_assignment(item))
            elif response.status_code not in (400, 404, 405):
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch shift assignments")

        if active_only:
            results = [row for row in results if row.get("status", row.get("is_active", True))]
        return results

    @classmethod
    def create_assignment(cls, payload: Dict[str, Any], assigned_by: str | None = None) -> Dict[str, Any]:
        body = cls._normalize_payload(payload, assigned_by=assigned_by)
        start = cls._parse_date(body["start_date"])
        end = cls._parse_date(body["end_date"])
        assert start is not None and end is not None
        cls._validate_no_overlap(body["employee_id"], start, end)

        response = cls._request(PRIMARY_TABLE, "POST", json_body=body)
        if response.status_code not in (200, 201):
            response = cls._request(LEGACY_TABLE, "POST", json_body=body)
        if response.status_code not in (200, 201):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create shift assignment")

        result = response.json()
        created = result[0] if isinstance(result, list) else result
        cls._record_history(
            employee_id=str(body["employee_id"]),
            old_shift_id=None,
            new_shift_id=body.get("shift_id"),
            effective_date=start,
            changed_by=assigned_by,
            reason=payload.get("reason") or "Shift assignment created",
        )
        return cls._enrich_assignment(created)

    @classmethod
    def update_assignment(cls, assignment_id: str, payload: Dict[str, Any], assigned_by: str | None = None) -> Optional[Dict[str, Any]]:
        existing = None
        for row in cls.get_assignments():
            if str(row.get("id")) == str(assignment_id):
                existing = row
                break
        if not existing:
            raise HTTPException(status_code=404, detail="Shift assignment not found")

        merged = {**existing, **payload}
        body = cls._normalize_payload(merged, assigned_by=assigned_by or existing.get("assigned_by"))
        start = cls._parse_date(body["start_date"])
        end = cls._parse_date(body["end_date"])
        assert start is not None and end is not None
        cls._validate_no_overlap(body["employee_id"], start, end, exclude_id=assignment_id)

        response = cls._request(PRIMARY_TABLE, "PATCH", json_body=body, params=f"?id=eq.{assignment_id}")
        if response.status_code not in (200, 204):
            response = cls._request(LEGACY_TABLE, "PATCH", json_body=body, params=f"?id=eq.{assignment_id}")
        if response.status_code not in (200, 204):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update shift assignment")

        cls._record_history(
            employee_id=str(body["employee_id"]),
            old_shift_id=existing.get("shift_id"),
            new_shift_id=body.get("shift_id"),
            effective_date=start,
            changed_by=assigned_by,
            reason=payload.get("reason") or "Shift assignment updated",
        )
        result = response.json()
        updated = result[0] if isinstance(result, list) and result else {**existing, **body}
        return cls._enrich_assignment(updated)

    @classmethod
    def delete_assignment(cls, assignment_id: str, *, changed_by: str | None = None, reason: str | None = None) -> bool:
        existing = next((row for row in cls.get_assignments() if str(row.get("id")) == str(assignment_id)), None)
        deleted_any = False
        for table in (PRIMARY_TABLE, LEGACY_TABLE):
            response = cls._request(table, "DELETE", params=f"?id=eq.{assignment_id}")
            if response.status_code in (200, 204):
                deleted_any = True
        if existing:
            start, _ = cls._assignment_window(existing)
            cls._record_history(
                employee_id=str(existing.get("employee_id") or ""),
                old_shift_id=existing.get("shift_id"),
                new_shift_id=None,
                effective_date=start or date.today(),
                changed_by=changed_by,
                reason=reason or "Shift assignment removed",
            )
        return deleted_any

    @classmethod
    def delete_employee_assignments(cls, employee_id: str) -> int:
        deleted = 0
        for assignment in cls.get_assignments(employee_id=employee_id):
            if cls.delete_assignment(str(assignment.get("id"))):
                deleted += 1
        return deleted

    @classmethod
    def _record_history(
        cls,
        *,
        employee_id: str,
        old_shift_id: str | None,
        new_shift_id: str | None,
        effective_date: date,
        changed_by: str | None,
        reason: str | None,
    ) -> None:
        body = {
            "employee_id": employee_id,
            "old_shift_id": old_shift_id,
            "new_shift_id": new_shift_id,
            "effective_date": effective_date.isoformat(),
            "changed_by": changed_by,
            "reason": reason,
            "changed_at": datetime.utcnow().isoformat(),
        }
        try:
            cls._request(HISTORY_TABLE, "POST", json_body=body)
        except HTTPException:
            pass

    @classmethod
    def get_history(
        cls,
        *,
        employee_id: str | None = None,
        shift_id: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> List[Dict[str, Any]]:
        params = "?select=*&order=changed_at.desc"
        if employee_id:
            params += f"&employee_id=eq.{employee_id}"
        if shift_id:
            params += f"&or=(old_shift_id.eq.{shift_id},new_shift_id.eq.{shift_id})"
        if from_date:
            params += f"&effective_date=gte.{from_date}"
        if to_date:
            params += f"&effective_date=lte.{to_date}"

        response = cls._request(HISTORY_TABLE, "GET", params=params)
        if response.status_code in (404, 400):
            return []
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch shift history")

        rows = response.json() or []
        enriched = []
        for row in rows:
            item = dict(row)
            for key in ("old_shift_id", "new_shift_id"):
                shift = shift_service.get_shift(str(item.get(key))) if item.get(key) else None
                if shift:
                    item[f"{key.replace('_id', '')}_name"] = shift.get("shift_name")
            enriched.append(item)
        return enriched


shift_assignment_service = ShiftAssignmentService()
