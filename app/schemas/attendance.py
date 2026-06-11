from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel


class AttendanceRecordCreate(BaseModel):
    employee_id: str
    attendance_date: date
    first_punch: Optional[datetime] = None
    last_punch: Optional[datetime] = None
    total_hours: Optional[float] = 0
    status: str


class AttendanceRecordUpdate(BaseModel):
    first_punch: Optional[datetime] = None
    last_punch: Optional[datetime] = None
    total_hours: Optional[float] = 0
    status: Optional[str] = None


class AttendanceRecordResponse(BaseModel):
    id: str
    employee_id: str
    attendance_date: date
    first_punch: Optional[datetime] = None
    last_punch: Optional[datetime] = None
    total_hours: Optional[float] = 0
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AttendanceListResponse(BaseModel):
    total: int
    page: int
    records: List[AttendanceRecordResponse]


class AttendanceSummary(BaseModel):
    total_employees: int
    present_today: int
    absent_today: int
    half_day: int
    leave_count: int
    half_day_today: int = 0
    leave_today: int = 0
    attendance_percentage: Optional[float] = None
