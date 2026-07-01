"""Shift master, assignments, notifications, and email API routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.middleware.auth import require_ceo
from app.models.profile import Profile
from app.schemas.auth import ErrorResponse
from app.services.automation_settings_service import automation_settings_service
from app.services.email_reports_service import email_reports_service
from app.services.notification_settings_service import notification_settings_service
from app.services.shift_assignment_service import shift_assignment_service
from app.services.shift_service import shift_service

router = APIRouter(
    tags=["shifts"],
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)


@router.get("/api/shifts", status_code=status.HTTP_200_OK)
def list_shifts(
    active_only: bool = Query(False),
    current_user: Profile = Depends(require_ceo),
):
    return shift_service.list_shifts(active_only=active_only)


@router.post("/api/shifts", status_code=status.HTTP_201_CREATED)
def create_shift(payload: dict, current_user: Profile = Depends(require_ceo)):
    return shift_service.create_shift(payload, created_by=str(current_user.id))


@router.put("/api/shifts/{shift_id}", status_code=status.HTTP_200_OK)
def update_shift(shift_id: str, payload: dict, current_user: Profile = Depends(require_ceo)):
    return shift_service.update_shift(shift_id, payload)


@router.delete("/api/shifts/{shift_id}", status_code=status.HTTP_200_OK)
def delete_shift(shift_id: str, current_user: Profile = Depends(require_ceo)):
    return {"deleted": shift_service.delete_shift(shift_id)}


@router.get("/api/shift-assignments", status_code=status.HTTP_200_OK)
def list_shift_assignments(
    employee_id: str | None = Query(None),
    shift_id: str | None = Query(None),
    active_only: bool = Query(False),
    current_user: Profile = Depends(require_ceo),
):
    return shift_assignment_service.get_assignments(
        employee_id=employee_id,
        shift_id=shift_id,
        active_only=active_only,
    )


@router.post("/api/shift-assignments", status_code=status.HTTP_201_CREATED)
def create_shift_assignment(payload: dict, current_user: Profile = Depends(require_ceo)):
    return shift_assignment_service.create_assignment(payload, assigned_by=str(current_user.id))


@router.put("/api/shift-assignments/{assignment_id}", status_code=status.HTTP_200_OK)
def update_shift_assignment(assignment_id: str, payload: dict, current_user: Profile = Depends(require_ceo)):
    return shift_assignment_service.update_assignment(assignment_id, payload, assigned_by=str(current_user.id))


@router.delete("/api/shift-assignments/{assignment_id}", status_code=status.HTTP_200_OK)
def delete_shift_assignment(assignment_id: str, current_user: Profile = Depends(require_ceo)):
    return {
        "deleted": shift_assignment_service.delete_assignment(
            assignment_id,
            changed_by=str(current_user.id),
        )
    }


@router.get("/api/shift-history", status_code=status.HTTP_200_OK)
def list_shift_history(
    employee_id: str | None = Query(None),
    shift_id: str | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    current_user: Profile = Depends(require_ceo),
):
    return shift_assignment_service.get_history(
        employee_id=employee_id,
        shift_id=shift_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/api/notification-settings", status_code=status.HTTP_200_OK)
def list_notification_settings(current_user: Profile = Depends(require_ceo)):
    return notification_settings_service.list_settings()


@router.put("/api/notification-settings/{employee_id}", status_code=status.HTTP_200_OK)
def update_notification_settings(employee_id: str, payload: dict, current_user: Profile = Depends(require_ceo)):
    try:
        return notification_settings_service.update_settings(employee_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/automation-settings", status_code=status.HTTP_200_OK)
def get_automation_settings(current_user: Profile = Depends(require_ceo)):
    return automation_settings_service.get_settings()


@router.put("/api/automation-settings", status_code=status.HTTP_200_OK)
def update_automation_settings(payload: dict, current_user: Profile = Depends(require_ceo)):
    return automation_settings_service.upsert_settings(payload)


@router.get("/api/email-history", status_code=status.HTTP_200_OK)
def list_email_history(
    employee_id: str | None = Query(None),
    email_type: str | None = Query(None),
    source: str | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    current_user: Profile = Depends(require_ceo),
):
    return email_reports_service.list_logs(
        employee_id=employee_id,
        email_type=email_type,
        source=source,
        from_date=from_date,
        to_date=to_date,
    )


def _previous_completed_month(month: int | None = None, year: int | None = None) -> tuple[int, int]:
    now = datetime.now()
    current_month = int(month) if month not in (None, "") and str(month).strip().isdigit() else now.month
    current_year = int(year) if year not in (None, "") and str(year).strip().isdigit() else now.year
    if current_month == 1:
        return 12, current_year - 1
    return current_month - 1, current_year


@router.post("/api/email/manual-send", status_code=status.HTTP_200_OK)
def manual_send_email(payload: dict, current_user: Profile = Depends(require_ceo)):
    email_type = str(payload.get("email_type") or "").strip().lower()
    employee_id = str(payload.get("employee_id") or "").strip()
    
    # Resolve email and cc_email dynamically from active shift assignment
    fallback_email = payload.get("recipient_email") or payload.get("email") or ""
    fallback_cc = payload.get("cc_email") or ""
    recipient_email, cc_email = email_reports_service.resolve_employee_emails(employee_id, fallback_email, fallback_cc)

    if not recipient_email:
        raise HTTPException(status_code=400, detail="recipient_email is required")

    if email_type not in {
        "monthly_report",
        "late_login_alert",
        "early_logout_alert",
        "missing_punch_alert",
        "escalation_alert",
    }:
        raise HTTPException(status_code=400, detail="Invalid email_type")

    month_value, year_value = _previous_completed_month(payload.get("month"), payload.get("year"))
    context = {
        "employee_id": employee_id,
        "employee_name": str(payload.get("employee_name") or "Employee"),
        "attendance_date": payload.get("attendance_date") or f"{year_value:04d}-{month_value:02d}-01",
        "month": month_value,
        "year": year_value,
        "month_label": datetime(year_value, month_value, 1).strftime("%B %Y"),
        "record": payload.get("record") or {},
        "assignment": payload.get("assignment") or {},
        "classification": payload.get("classification") or {},
        "template": payload.get("template"),
        "date_range": payload.get("date_range"),
    }

    try:
        activity = email_reports_service.log_activity(
            employee_id=employee_id,
            employee_name=str(payload.get("employee_name") or "Employee"),
            recipient_email=str(recipient_email or ""),
            cc_email=str(cc_email or ""),
            email_type=email_type,
            status="SENT",
            context=context,
            source="MANUAL",
            sent_by=str(current_user.id),
            force=True,  # bypass monthly dedup for manual sends
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"status": "ok", "message": f"{email_type.replace('_', ' ').title()} email sent", "activity": activity}
