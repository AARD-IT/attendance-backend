"""
CEO API endpoints.
CEO-specific dashboard and management endpoints.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.middleware.auth import require_ceo
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard_service import dashboard_service
from app.services.email_preferences_service import email_preferences_service
from app.services.email_reports_service import email_reports_service
from app.services.shift_assignment_service import shift_assignment_service
from app.models.profile import Profile
from app.schemas.auth import ErrorResponse


def _previous_completed_month(month: int | None = None, year: int | None = None) -> tuple[int, int]:
    now = datetime.now()
    current_month = int(month) if month not in (None, "") and str(month).strip().isdigit() else now.month
    current_year = int(year) if year not in (None, "") and str(year).strip().isdigit() else now.year
    if current_month == 1:
        return 12, current_year - 1
    return current_month - 1, current_year


router = APIRouter(
    prefix="/api/ceo",
    tags=["ceo"],
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    status_code=status.HTTP_200_OK,
    summary="CEO Dashboard",
    description="Get CEO dashboard with company statistics"
)
def get_ceo_dashboard(current_user: Profile = Depends(require_ceo)):
    """
    CEO Dashboard endpoint.
    
    **Access:** CEO role required
    
    **Response:**
    - Dashboard message
    - User information
    - Company statistics (employees, sessions, pending attendance)
    """
    return dashboard_service.build_ceo_dashboard(current_user)


@router.get("/shift-assignments", status_code=status.HTTP_200_OK)
def list_shift_assignments(current_user: Profile = Depends(require_ceo)):
    return shift_assignment_service.get_assignments()


@router.post("/shift-assignments", status_code=status.HTTP_201_CREATED)
def create_shift_assignment(payload: dict, current_user: Profile = Depends(require_ceo)):
    if not payload.get("employee_id"):
        raise HTTPException(status_code=400, detail="employee_id is required")
    return shift_assignment_service.create_assignment(payload)


@router.put("/shift-assignments/{assignment_id}", status_code=status.HTTP_200_OK)
def update_shift_assignment(assignment_id: str, payload: dict, current_user: Profile = Depends(require_ceo)):
    return shift_assignment_service.update_assignment(assignment_id, payload)


@router.delete("/shift-assignments/{assignment_id}", status_code=status.HTTP_200_OK)
def delete_shift_assignment(assignment_id: str, current_user: Profile = Depends(require_ceo)):
    return {"deleted": shift_assignment_service.delete_assignment(assignment_id)}


@router.delete("/shift-assignments/employee/{employee_id}", status_code=status.HTTP_200_OK)
def delete_employee_shift_assignments(employee_id: str, current_user: Profile = Depends(require_ceo)):
    return {"deleted": shift_assignment_service.delete_employee_assignments(employee_id)}


@router.get("/email-preferences", status_code=status.HTTP_200_OK)
def list_email_preferences(current_user: Profile = Depends(require_ceo)):
    return email_preferences_service.list_preferences()


@router.get("/email-logs", status_code=status.HTTP_200_OK)
def list_email_logs(current_user: Profile = Depends(require_ceo)):
    return email_reports_service.list_logs()


@router.post("/email-preferences/ensure", status_code=status.HTTP_201_CREATED)
def ensure_email_preference(payload: dict, current_user: Profile = Depends(require_ceo)):
    employee_id = payload.get("employee_id")
    employee_name = payload.get("employee_name") or "Employee"
    employee_email = payload.get("employee_email") or ""

    if not employee_id:
        raise HTTPException(status_code=400, detail="employee_id is required")

    return email_preferences_service.ensure_preference(employee_id, employee_name, employee_email)


@router.post("/email-reports/monthly-report", status_code=status.HTTP_200_OK)
def send_monthly_report(payload: dict, current_user: Profile = Depends(require_ceo)):
    recipient_email = payload.get("recipient_email") or payload.get("email")
    if not recipient_email:
        raise HTTPException(status_code=400, detail="recipient_email is required")
    try:
        month_value, year_value = _previous_completed_month(payload.get("month"), payload.get("year"))
        context = {
            "employee_id": str(payload.get("employee_id") or ""),
            "employee_name": str(payload.get("employee_name") or "Employee"),
            "attendance_date": payload.get("attendance_date") or f"{year_value:04d}-{month_value:02d}-01",
            "month": month_value,
            "year": year_value,
            "month_label": datetime(year_value, month_value, 1).strftime("%B %Y"),
            "record": payload.get("record"),
            "assignment": payload.get("assignment"),
            "classification": payload.get("classification"),
        }
        activity = email_reports_service.log_activity(
            employee_id=str(payload.get("employee_id") or ""),
            employee_name=str(payload.get("employee_name") or "Employee"),
            recipient_email=str(recipient_email),
            email_type="monthly_report",
            status="SENT",
            context=context,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "ok", "message": "Monthly attendance report email sent", "activity": activity}


@router.post("/email-reports/late-login", status_code=status.HTTP_200_OK)
def send_late_login_alert(payload: dict, current_user: Profile = Depends(require_ceo)):
    recipient_email = payload.get("recipient_email") or payload.get("email")
    if not recipient_email:
        raise HTTPException(status_code=400, detail="recipient_email is required")
    try:
        attendance_date = payload.get("attendance_date") or None
        context = {
            "employee_id": str(payload.get("employee_id") or ""),
            "employee_name": str(payload.get("employee_name") or "Employee"),
            "attendance_date": attendance_date,
            "month": int(payload.get("month", 0)) if str(payload.get("month") or "").strip().isdigit() else None,
            "year": int(payload.get("year", 0)) if str(payload.get("year") or "").strip().isdigit() else None,
            "record": payload.get("record"),
            "assignment": payload.get("assignment"),
            "classification": payload.get("classification"),
        }
        activity = email_reports_service.log_activity(
            employee_id=str(payload.get("employee_id") or ""),
            employee_name=str(payload.get("employee_name") or "Employee"),
            recipient_email=str(recipient_email),
            email_type="late_login_alert",
            status="SENT",
            context=context,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "ok", "message": "Late login alert email sent", "activity": activity}


@router.post("/email-reports/early-logout", status_code=status.HTTP_200_OK)
def send_early_logout_alert(payload: dict, current_user: Profile = Depends(require_ceo)):
    recipient_email = payload.get("recipient_email") or payload.get("email")
    if not recipient_email:
        raise HTTPException(status_code=400, detail="recipient_email is required")
    try:
        attendance_date = payload.get("attendance_date") or None
        context = {
            "employee_id": str(payload.get("employee_id") or ""),
            "employee_name": str(payload.get("employee_name") or "Employee"),
            "attendance_date": attendance_date,
            "month": int(payload.get("month", 0)) if str(payload.get("month") or "").strip().isdigit() else None,
            "year": int(payload.get("year", 0)) if str(payload.get("year") or "").strip().isdigit() else None,
            "record": payload.get("record"),
            "assignment": payload.get("assignment"),
            "classification": payload.get("classification"),
        }
        activity = email_reports_service.log_activity(
            employee_id=str(payload.get("employee_id") or ""),
            employee_name=str(payload.get("employee_name") or "Employee"),
            recipient_email=str(recipient_email),
            email_type="early_logout_alert",
            status="SENT",
            context=context,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "ok", "message": "Early logout alert email sent", "activity": activity}


@router.patch("/email-preferences/{employee_id}", status_code=status.HTTP_200_OK)
def update_email_preference(employee_id: str, payload: dict, current_user: Profile = Depends(require_ceo)):
    mode_type = payload.get("mode_type")
    mode_value = payload.get("mode_value")

    if not mode_type or mode_type not in {"monthly_report_mode", "late_login_mode", "early_logout_mode"}:
        raise HTTPException(status_code=400, detail="Invalid mode_type")
    if mode_value not in {"manual", "auto"}:
        raise HTTPException(status_code=400, detail="Invalid mode_value")

    return email_preferences_service.update_preference(employee_id, mode_type, mode_value)

