"""
Attendance service layer.

Uses Supabase REST API to store and retrieve attendance_records.
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional
import logging

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.models.attendance import AttendanceRecord
from app.models.profile import Profile


logger = logging.getLogger(__name__)


SUPABASE_BASE = settings.SUPABASE_URL.rstrip('/')
SUPABASE_HEADERS = {
    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}


class AttendanceService:
    SUPABASE_BASE = settings.SUPABASE_URL.rstrip('/')
    SUPABASE_HEADERS = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    @staticmethod
    def get_all_attendance(page: int = 1, limit: int = 20, employee_id: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        params["limit"] = limit
        params["offset"] = (page - 1) * limit

        if employee_id:
            params["employee_id"] = f"eq.{employee_id}"

        if start_date or end_date:
            date_filters = []
            if start_date:
                date_filters.append(f"gte.{start_date}")
            if end_date:
                date_filters.append(f"lte.{end_date}")
            params["attendance_date"] = date_filters

        url = f"{AttendanceService.SUPABASE_BASE}/rest/v1/attendance_records"

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    url,
                    headers={**AttendanceService.SUPABASE_HEADERS, "Prefer": "count=exact"},
                    params=params,
                )

            if response.status_code != 200:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch attendance records")

            records = response.json()
            total = 0
            content_range = response.headers.get("Content-Range") or response.headers.get("content-range")
            if content_range:
                try:
                    total = int(content_range.split("/")[-1])
                except (ValueError, IndexError):
                    total = len(records)
            else:
                total = len(records)

            return {"total": total, "page": page, "records": records}

        except httpx.RequestError as e:
            logger.error(f"Error fetching attendance: {str(e)}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Attendance service unavailable")

    @staticmethod
    def get_daily_attendance(page: int = 1, limit: int = 20, employee_id: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        params["limit"] = limit
        params["offset"] = (page - 1) * limit

        if employee_id:
            params["employee_id"] = f"eq.{employee_id}"

        if start_date or end_date:
            date_filters = []
            if start_date:
                date_filters.append(f"gte.{start_date}")
            if end_date:
                date_filters.append(f"lte.{end_date}")
            params["attendance_date"] = date_filters

        url = f"{AttendanceService.SUPABASE_BASE}/rest/v1/attendance_daily"

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    url,
                    headers={**AttendanceService.SUPABASE_HEADERS, "Prefer": "count=exact"},
                    params=params,
                )

            if response.status_code != 200:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch daily attendance records")

            records = response.json()
            total = 0
            content_range = response.headers.get("Content-Range") or response.headers.get("content-range")
            if content_range:
                try:
                    total = int(content_range.split("/")[-1])
                except (ValueError, IndexError):
                    total = len(records)
            else:
                total = len(records)

            return {"total": total, "page": page, "records": records}

        except httpx.RequestError as e:
            logger.error(f"Error fetching daily attendance: {str(e)}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Attendance service unavailable")

    @staticmethod
    def get_employee_attendance(employee_id: str) -> List[Dict[str, Any]]:
        url = f"{AttendanceService.SUPABASE_BASE}/rest/v1/attendance_records"
        params = {"employee_id": f"eq.{employee_id}", "order": "attendance_date.desc"}

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=AttendanceService.SUPABASE_HEADERS, params=params)

            if response.status_code != 200:
                return []

            return response.json()
        except httpx.RequestError:
            return []

    @staticmethod
    def get_attendance_summary() -> Dict[str, Any]:
        # compute stats for today
        today = date.today().isoformat()
        url = f"{AttendanceService.SUPABASE_BASE}/rest/v1/attendance_records"

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, headers=AttendanceService.SUPABASE_HEADERS, params={"attendance_date": f"eq.{today}"})

            if resp.status_code != 200:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch attendance summary")

            rows = resp.json()
            present = sum(1 for r in rows if r.get("status") == "PRESENT")
            absent = sum(1 for r in rows if r.get("status") == "ABSENT")
            half = sum(1 for r in rows if r.get("status") == "HALF_DAY")
            leave = sum(1 for r in rows if r.get("status") == "LEAVE")

            # total employees: only Minerva-synced employee master profiles should count
            with httpx.Client(timeout=10.0) as client:
                profiles_resp = client.get(f"{AttendanceService.SUPABASE_BASE}/rest/v1/profiles", headers=AttendanceService.SUPABASE_HEADERS)

            profiles = []
            if profiles_resp.status_code == 200:
                try:
                    profiles = profiles_resp.json()
                except ValueError:
                    profiles = []

            total_employees = sum(
                1
                for profile in profiles
                if str(profile.get('role') or '').upper() == 'EMPLOYEE'
                and (str(profile.get('emp_code') or '').strip() or str(profile.get('minerva_employee_id') or '').strip())
            )

            attendance_percentage = None
            if total_employees > 0:
                attendance_percentage = round(((present + half * 0.5) / total_employees) * 100, 2)

            return {
                "total_employees": total_employees,
                "present_today": present,
                "absent_today": absent,
                "half_day": half,
                "leave_count": leave,
                "half_day_today": half,
                "leave_today": leave,
                "attendance_percentage": attendance_percentage,
            }

        except httpx.RequestError as e:
            logger.error(f"Error computing attendance summary: {str(e)}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Attendance service unavailable")

    @staticmethod
    def create_attendance_record(payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{AttendanceService.SUPABASE_BASE}/rest/v1/attendance_records"
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=payload, headers={**AttendanceService.SUPABASE_HEADERS, "Prefer": "return=representation"})

            if response.status_code not in (200, 201):
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create attendance record")

            result = response.json()
            return result[0] if isinstance(result, list) and len(result) > 0 else result

        except httpx.RequestError as e:
            logger.error(f"Error creating attendance record: {str(e)}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Attendance service unavailable")

    @staticmethod
    def update_attendance_record(record_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url = f"{AttendanceService.SUPABASE_BASE}/rest/v1/attendance_records"
        params = {"id": f"eq.{record_id}"}
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.patch(url, params=params, json=payload, headers={**AttendanceService.SUPABASE_HEADERS, "Prefer": "return=representation"})

            if response.status_code not in (200, 204):
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update attendance record")

            result = response.json()
            return result[0] if isinstance(result, list) and len(result) > 0 else None

        except httpx.RequestError as e:
            logger.error(f"Error updating attendance record: {str(e)}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Attendance service unavailable")

    @staticmethod
    def delete_attendance_record(record_id: str) -> bool:
        url = f"{AttendanceService.SUPABASE_BASE}/rest/v1/attendance_records"
        params = {"id": f"eq.{record_id}"}
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.delete(url, params=params, headers=AttendanceService.SUPABASE_HEADERS)

            return response.status_code in (200, 204)
        except httpx.RequestError as e:
            logger.error(f"Error deleting attendance record: {str(e)}")
            return False


# Global instance
attendance_service = AttendanceService()
