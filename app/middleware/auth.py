"""
Authentication middleware for FastAPI.
Handles JWT validation using Supabase JWKS and role-based access control.
"""

import logging
from typing import Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.session_validator import SessionValidator
from app.services.auth_service import auth_service
from app.services.token_service import token_service
from app.models.profile import Profile
from app.core.config import settings


logger = logging.getLogger(__name__)

# Security scheme for Swagger documentation
security = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Profile:
    """
    Get current authenticated user from JWT token.
    
    Validates:
    - JWT signature using Supabase JWKS
    - Token expiration
    - Session is still active with Supabase
    
    Args:
        credentials: HTTP Bearer credentials
        
    Returns:
        Profile: Current user profile
        
    Raises:
        HTTPException: If token is invalid, expired, or session revoked
    """
    access_token = credentials.credentials
    
    try:
        # Validate JWT token using Supabase JWKS
        logger.debug("Validating JWT token signature")
        claims = token_service.validate_supabase_token(access_token)

        user_id = claims.get("sub")
        if not user_id:
            logger.warning("Token missing 'sub' claim")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID"
            )

        # Reject tokens that are present in the revocation list
        token_service.check_token_revocation(access_token, user_id)

        # Validate session is still active with Supabase (Option A)
        if settings.SESSION_VALIDATION_ENABLED:
            logger.debug(f"Verifying session is active for user: {user_id}")
            try:
                SessionValidator.validate_session(access_token, user_id)
            except HTTPException as exc:
                if exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR:
                    logger.warning("Session verification unavailable; treating request as unauthorized")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Session is invalid or has been revoked"
                    )
                raise

        # Fetch user profile from database
        logger.debug(f"Fetching profile for user: {user_id}")
        profile = auth_service.get_profile(user_id)
        if not profile:
            logger.warning(f"Profile not found for user: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User profile not found"
            )
        
        logger.debug(f"User authenticated: {user_id}, role: {profile.role}")
        return profile
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during authentication: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )


def role_guard(required_role: str) -> Callable:
    """
    Create a role-based access control guard.
    
    Args:
        required_role: Required role to access endpoint (e.g., "CEO", "EMPLOYEE")
        
    Returns:
        Callable: Dependency function for FastAPI
        
    Raises:
        HTTPException: If user doesn't have required role
    """
    def _guard(current_user: Profile = Depends(get_current_user)) -> Profile:
        """Check if user has required role."""
        if current_user.role != required_role:
            logger.warning(
                f"Access denied for user {current_user.id}: "
                f"required {required_role}, has {current_user.role}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_user
    
    return _guard


def require_ceo(current_user: Profile = Depends(get_current_user)) -> Profile:
    """
    Require CEO role.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Profile: User profile if authorized
        
    Raises:
        HTTPException: If user is not CEO
    """
    if current_user.role != "CEO":
        logger.warning(f"CEO access denied for user {current_user.id} with role {current_user.role}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CEO access required"
        )
    return current_user


def require_employee(current_user: Profile = Depends(get_current_user)) -> Profile:
    """
    Require EMPLOYEE role.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Profile: User profile if authorized
        
    Raises:
        HTTPException: If user is not EMPLOYEE
    """
    if current_user.role != "EMPLOYEE":
        logger.warning(f"Employee access denied for user {current_user.id} with role {current_user.role}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee access required"
        )
    return current_user

