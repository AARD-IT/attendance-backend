"""
Security utilities for JWT validation and token handling.
Handles Supabase JWT verification and token extraction.
"""

from typing import Dict, Optional, Any

from fastapi import HTTPException, status

from app.services.token_service import token_service


def validate_jwt(token: str) -> Dict[str, Any]:
    """
    Validate JWT token using Supabase JWKS.

    Args:
        token: The JWT token to validate

    Returns:
        Dict: Decoded token claims
    """
    return token_service.validate_supabase_token(token)


def get_token_from_header(authorization: Optional[str]) -> str:
    """
    Extract Bearer token from Authorization header.

    Args:
        authorization: The Authorization header value

    Returns:
        str: The token

    Raises:
        HTTPException: If token format is invalid
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return parts[1]
