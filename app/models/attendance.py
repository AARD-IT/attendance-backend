from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel


class AttendanceRecord(BaseModel):
    id: Optional[str]
    employee_id: str
    attendance_date: date
    first_punch: Optional[datetime] = None
    last_punch: Optional[datetime] = None
    total_hours: Optional[float] = 0
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

