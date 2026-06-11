from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class Profile(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    role: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
