"""
Service layer for Supabase JWT validation and token revocation.

This module centralizes secure JWT validation and the revocation workflow
for Supabase-issued access tokens.
"""

import hashlib
import logging
from typing import Any, Dict, Optional

import jwt
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.jwt_validator import SupabaseJWTValidator
from app.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class TokenService:
    """Service for handling Supabase access token validation and revocation."""

    @staticmethod
    def get_unverified_claims(token: str) -> Dict[str, Any]:
        """Return token claims without verifying signature or expiration."""
        try:
            return jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": False},
            )
        except jwt.DecodeError as exc:
            logger.warning(f"Invalid token format for revocation lookup: {str(exc)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format",
            )

    @staticmethod
    def get_token_identifier(token: str, claims: Optional[Dict[str, Any]] = None) -> str:
        """Return a deterministic token identifier for revocation lookup."""
        if claims is None:
            claims = TokenService.get_unverified_claims(token)

        jti = claims.get("jti")
        if jti:
            return str(jti)

        # Fallback: deterministic hash of the token when JTI is missing
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def validate_supabase_token(token: str) -> Dict[str, Any]:
        """Validate a Supabase-issued JWT and return its claims."""
        claims = SupabaseJWTValidator.validate_token(token)
        if not claims.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
            )
        return claims

    @staticmethod
    def check_token_revocation(token: str, user_id: Optional[str] = None) -> None:
        """Reject request if token is found in the revocation list."""
        if not settings.TOKEN_REVOCATION_ENABLED:
            return

        jti = TokenService.get_token_identifier(token)
        if SupabaseClient.check_revoked_token(jti, user_id):
            logger.warning(f"Token revoked for user_id={user_id}, jti={jti}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )

    @staticmethod
    def revoke_token(access_token: str, user_id: str) -> bool:
        """Add the given access token to the revocation list."""
        claims: Optional[Dict[str, Any]]

        try:
            claims = SupabaseJWTValidator.validate_token(access_token)
        except HTTPException:
            logger.debug("Token validation failed during revoke_token; using unverified claims")
            claims = None

        jti = TokenService.get_token_identifier(access_token, claims)
        token_hash = hash(access_token)

        result = SupabaseClient.revoke_token(
            user_id=user_id,
            jti=jti,
            token_hash=token_hash,
        )

        if result:
            logger.info(f"Revoked token stored for user_id={user_id}, jti={jti}")
        else:
            logger.warning(f"Failed to store revoked token for user_id={user_id}, jti={jti}")

        return result


# Global token service instance
token_service = TokenService()
