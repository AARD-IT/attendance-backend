"""Simple CRUD service for employee shift assignments."""

from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

SUPABASE_BASE = settings.SUPABASE_URL.rstrip('/')
SUPABASE_HEADERS = {
    'apikey': settings.SUPABASE_SERVICE_ROLE_KEY,
    'Authorization': f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    'Content-Type': 'application/json',
}


class ShiftAssignmentService:
    @staticmethod
    def _request(table: str, method: str, *, json_body: Dict[str, Any] | None = None, params: str = '') -> Any:
        url = f"{SUPABASE_BASE}/rest/v1/{table}"
        if params:
            url = f"{url}{params}"
        headers = {**SUPABASE_HEADERS}
        if json_body is not None:
            headers['Prefer'] = 'return=representation'
        try:
            with httpx.Client(timeout=10.0) as client:
                if method == 'GET':
                    response = client.get(url, headers=headers)
                elif method == 'POST':
                    response = client.post(url, json=json_body, headers=headers)
                elif method == 'DELETE':
                    response = client.delete(url, headers=headers)
                else:
                    response = client.patch(url, json=json_body, headers=headers)
            return response
        except httpx.RequestError as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Supabase request failed') from exc

    @staticmethod
    def get_assignments() -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for table in ('shift_assignments', 'employee_shift_assignments'):
            response = ShiftAssignmentService._request(table, 'GET')
            if response.status_code == 200:
                payload = response.json()
                if isinstance(payload, list):
                    results.extend([item for item in payload if isinstance(item, dict)])
                continue
            if response.status_code not in (400, 404, 405):
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to fetch shift assignments')
        return results

    @staticmethod
    def create_assignment(payload: Dict[str, Any]) -> Dict[str, Any]:
        for table in ('shift_assignments', 'employee_shift_assignments'):
            response = ShiftAssignmentService._request(table, 'POST', json_body=payload)
            if response.status_code in (200, 201):
                result = response.json()
                return result[0] if isinstance(result, list) else result
            if response.status_code not in (400, 404, 405):
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to create shift assignment')
        return payload

    @staticmethod
    def update_assignment(assignment_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for table in ('shift_assignments', 'employee_shift_assignments'):
            response = ShiftAssignmentService._request(table, 'PATCH', json_body=payload, params=f"?id=eq.{assignment_id}")
            if response.status_code in (200, 204):
                result = response.json()
                return result[0] if isinstance(result, list) else result
            if response.status_code not in (400, 404, 405):
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to update shift assignment')
        return payload

    @staticmethod
    def delete_assignment(assignment_id: str) -> bool:
        deleted_any = False
        for table in ('shift_assignments', 'employee_shift_assignments'):
            response = ShiftAssignmentService._request(table, 'DELETE', params=f"?id=eq.{assignment_id}")
            if response.status_code in (200, 204):
                deleted_any = True
                continue
            if response.status_code not in (400, 404, 405):
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to delete shift assignment')
        return deleted_any

    @staticmethod
    def delete_employee_assignments(employee_id: str) -> int:
        deleted = 0
        for table in ('shift_assignments', 'employee_shift_assignments'):
            response = ShiftAssignmentService._request(table, 'DELETE', params=f"?employee_id=eq.{employee_id}")
            if response.status_code in (200, 204):
                try:
                    deleted += len(response.json()) if isinstance(response.json(), list) else 1
                except Exception:
                    deleted += 1
                continue
            if response.status_code not in (400, 404, 405):
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to delete employee shift assignments')
        return deleted


shift_assignment_service = ShiftAssignmentService()
