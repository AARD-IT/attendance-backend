"""
Pydantic schemas for authentication endpoints.
Defines request and response models for login, signup, and auth operations.
"""

from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Login request model."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="User password")
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "securepassword123"
            }
        }


class RegisterRequest(BaseModel):
    """Register request model."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="User password")
    full_name: str = Field(..., min_length=1, description="User full name")
    role: str = Field(..., description="User role (CEO or EMPLOYEE)")

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "securepassword123",
                "full_name": "Jane Doe",
                "role": "EMPLOYEE"
            }
        }


class UserResponse(BaseModel):
    """User response model."""
    id: str = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    role: str = Field(..., description="User role (CEO or EMPLOYEE)")
    full_name: Optional[str] = Field(None, description="User full name")
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "ceo@example.com",
                "role": "CEO",
                "full_name": "John Doe"
            }
        }


class LoginResponse(BaseModel):
    """Login response model. Used for both login and signup endpoints."""
    success: bool = Field(True, description="Operation success status")
    message: Optional[str] = Field(None, description="Response message")
    user: UserResponse = Field(..., description="User information")
    access_token: Optional[str] = Field(None, description="JWT access token (None for signup, user must log in manually)")
    token_type: str = Field("bearer", description="Token type")
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Login successful",
                "user": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "email": "ceo@example.com",
                    "role": "CEO",
                    "full_name": "John Doe"
                },
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer"
            }
        }


class CurrentUserResponse(BaseModel):
    """Current user information response."""
    id: str = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    role: str = Field(..., description="User role")
    full_name: Optional[str] = Field(None, description="User full name")
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "employee@example.com",
                "role": "EMPLOYEE",
                "full_name": "Jane Smith"
            }
        }


class LogoutResponse(BaseModel):
    """Logout response model."""
    success: bool = Field(True, description="Operation success status")
    message: str = Field("Logged out successfully", description="Response message")
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Logged out successfully"
            }
        }


class ErrorResponse(BaseModel):
    """Error response model."""
    success: bool = Field(False, description="Operation success status")
    detail: str = Field(..., description="Error message")
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "success": False,
                "detail": "Invalid credentials"
            }
        }

