"""
Employee API endpoints.
Employee-specific dashboard and attendance endpoints.
"""

from fastapi import APIRouter, Depends, status

from app.middleware.auth import require_employee
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard_service import dashboard_service
from app.models.profile import Profile
from app.schemas.auth import ErrorResponse


router = APIRouter(
    prefix="/api/employee",
    tags=["employee"],
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
    summary="Employee Dashboard",
    description="Get employee dashboard with attendance status"
)
def get_employee_dashboard(current_user: Profile = Depends(require_employee)):
    """
    Employee Dashboard endpoint.
    
    **Access:** EMPLOYEE role required
    
    **Response:**
    - Dashboard message
    - User information
    - Attendance status (check-in/out, hours worked)
    """
    return dashboard_service.build_employee_dashboard(current_user)

