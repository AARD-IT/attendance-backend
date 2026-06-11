"""
Pydantic schemas for dashboard endpoints.
Defines request and response models for dashboard operations.
"""

from typing import Optional
from pydantic import BaseModel, Field
from app.schemas.auth import UserResponse


class DashboardResponse(BaseModel):
    """Dashboard response model."""
    message: str = Field(..., description="Dashboard message")
    user: UserResponse = Field(..., description="User information")
    role: str = Field(..., description="User role")
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "message": "CEO Dashboard",
                "user": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "email": "ceo@example.com",
                    "role": "CEO",
                    "full_name": "John Doe"
                },
                "role": "CEO"
            }
        }


class CEODashboardData(BaseModel):
    """CEO Dashboard specific data."""
    total_employees: int = Field(0, description="Total number of employees")
    active_sessions: int = Field(0, description="Number of active employee sessions")
    pending_attendance: int = Field(0, description="Pending attendance records")
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "total_employees": 50,
                "active_sessions": 25,
                "pending_attendance": 5
            }
        }


class EmployeeDashboardData(BaseModel):
    """Employee Dashboard specific data."""
    checkin_status: str = Field("checked_out", description="Current check-in status")
    last_checkin: Optional[str] = Field(None, description="Last check-in timestamp")
    last_checkout: Optional[str] = Field(None, description="Last check-out timestamp")
    today_hours: float = Field(0.0, description="Hours worked today")
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "checkin_status": "checked_in",
                "last_checkin": "2024-01-15T09:00:00Z",
                "last_checkout": None,
                "today_hours": 2.5
            }
        }

