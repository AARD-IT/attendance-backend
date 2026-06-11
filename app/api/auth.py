"""
Authentication API endpoints.
Handles login, logout, and current user endpoints.
"""

from fastapi import APIRouter, Depends, Security, status, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    LoginResponse,
    CurrentUserResponse,
    LogoutResponse,
    ErrorResponse
)
from app.services.auth_service import auth_service
from app.middleware.auth import get_current_user
from app.models.profile import Profile


router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)

security = HTTPBearer()


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="User Login",
    description="Authenticate user with email and password"
)
def login(payload: LoginRequest):
    """
    Login endpoint.
    
    **Request:**
    - `email`: User email address
    - `password`: User password
    
    **Response:**
    - `success`: Login status
    - `user`: User information including role
    - `access_token`: JWT token for authenticated requests
    """
    try:
        auth_payload = auth_service.login(payload.email, payload.password)
        return {
            "success": True,
            "message": "Login successful",
            "user": auth_payload["user"],
            "access_token": auth_payload["access_token"],
            "token_type": "bearer"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post(
    "/signup",
    response_model=LoginResponse,
    status_code=status.HTTP_201_CREATED,
    summary="User Sign Up",
    description="Create a new user account and return authentication details"
)
def signup(payload: RegisterRequest):
    """
    Signup endpoint.
    
    **Request:**
    - `email`: User email address
    - `password`: User password
    - `full_name`: User full name
    - `role`: User role (CEO or EMPLOYEE)
    
    **Response:**
    - `success`: Signup status
    - `user`: User information including role
    - `access_token`: JWT token for authenticated requests
    """
    try:
        auth_payload = auth_service.signup(payload.email, payload.password, payload.full_name, payload.role)
        return {
            "success": True,
            "message": "Signup successful",
            "user": auth_payload["user"],
            "access_token": auth_payload["access_token"],
            "token_type": "bearer"
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Signup failed"
        )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="User Logout",
    description="Logout current user and invalidate session"
)
def logout(
    credentials: HTTPAuthorizationCredentials = Security(security),
    current_user: Profile = Depends(get_current_user)
):
    """
    Logout endpoint.
    
    **Headers:**
    - `Authorization`: Bearer token
    
    **Response:**
    - `success`: Logout status
    - `message`: Logout message
    
    Performs:
    1. Invalidates session in Supabase
    2. Adds token to revocation list
    3. Logs the logout event
    """
    try:
        access_token = credentials.credentials
        auth_service.logout(access_token, current_user.id)
        return {
            "success": True,
            "message": "Logged out successfully"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Current User",
    description="Get current authenticated user information"
)
def get_current_user_info(current_user: Profile = Depends(get_current_user)):
    """
    Get current user endpoint.
    
    **Headers:**
    - `Authorization`: Bearer token
    
    **Response:**
    - User ID, email, role, and full name
    """
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "full_name": current_user.full_name
    }

