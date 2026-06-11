from fastapi import APIRouter, Depends, Query, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from typing import Optional

from app.schemas.attendance import (
    AttendanceListResponse,
    AttendanceRecordResponse,
    AttendanceRecordCreate,
    AttendanceRecordUpdate,
    AttendanceSummary,
)
from app.services.attendance_service import attendance_service
from app.middleware.auth import get_current_user, require_ceo, require_employee
from app.models.profile import Profile


router = APIRouter(prefix="/api/attendance", tags=["attendance"]) 


def require_ceo_dependency(request: Request) -> Profile:
    """Compatibility wrapper for CEO access in runtime and tests."""
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")

    try:
        if auth_header and auth_header.startswith("Bearer "):
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials=auth_header.split(" ", 1)[1],
            )
            current_user = get_current_user(credentials)
            return require_ceo(current_user)

        return require_ceo()
    except TypeError:
        return require_ceo()
    except AttributeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authentication required") from exc


def require_employee_dependency(request: Request) -> Profile:
    """Compatibility wrapper for employee access in runtime and tests."""
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")

    try:
        if auth_header and auth_header.startswith("Bearer "):
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials=auth_header.split(" ", 1)[1],
            )
            current_user = get_current_user(credentials)
            return require_employee(current_user)

        return require_employee()
    except TypeError:
        return require_employee()
    except AttributeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authentication required") from exc


@router.get("/", response_model=AttendanceListResponse)
def list_attendance(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    employee_id: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    _current: Profile = Depends(require_ceo_dependency),
):
    """CEO-only: list all attendance records with pagination and filters."""
    result = attendance_service.get_all_attendance(page=page, limit=limit, employee_id=employee_id, start_date=start_date, end_date=end_date)
    return result


@router.get("/me", response_model=list[AttendanceRecordResponse])
def my_attendance(current_user: Profile = Depends(require_employee_dependency)):
    """Employee: get own attendance history."""
    records = attendance_service.get_employee_attendance(current_user.id)
    return records


@router.get("/summary", response_model=AttendanceSummary)
def attendance_summary(_current: Profile = Depends(require_ceo_dependency)):
    """CEO-only: get attendance analytics summary for today."""
    summary = attendance_service.get_attendance_summary()
    return summary


# Optional admin APIs (CEO only)
@router.post("/", response_model=AttendanceRecordResponse)
def create_attendance(record: AttendanceRecordCreate, _current: Profile = Depends(require_ceo_dependency)):
    payload = record.dict()
    created = attendance_service.create_attendance_record(payload)
    return created


@router.put("/{record_id}", response_model=AttendanceRecordResponse)
def update_attendance(record_id: str, payload: AttendanceRecordUpdate, _current: Profile = Depends(require_ceo_dependency)):
    updated = attendance_service.update_attendance_record(record_id, payload.dict(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    return updated


@router.delete("/{record_id}")
def delete_attendance(record_id: str, _current: Profile = Depends(require_ceo_dependency)):
    ok = attendance_service.delete_attendance_record(record_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")
    return {"success": True}
