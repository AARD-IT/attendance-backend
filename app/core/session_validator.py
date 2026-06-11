"""
Session validation for revocation checking.
Implements enterprise-grade session validation with two options:

Option A (Preferred): Verify session is still active with Supabase Auth API
Option B (Fallback): Token revocation list stored in database

This module handles:
- Session existence verification with Supabase
- Token revocation list management (Option B)
- Graceful error handling
- Structured logging
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.db.supabase import SupabaseClient


logger = logging.getLogger(__name__)


class SessionValidator:
    """
    Validates user sessions using Supabase as source of truth.
    
    Primary strategy (Option A):
    - Verify session is still active with Supabase Auth API
    - Call /auth/v1/user with access token
    - If Supabase returns 401, session is invalid/revoked
    """
    
    @staticmethod
    def verify_session_active(access_token: str, user_id: str) -> bool:
        """
        Verify that a session is still active in Supabase.
        
        Calls Supabase Auth API to verify the token is still valid
        and the user session hasn't been revoked.
        
        Args:
            access_token: The JWT access token
            user_id: The user ID to verify
            
        Returns:
            bool: True if session is active, False otherwise
            
        Raises:
            HTTPException: If verification fails unexpectedly
        """
        url = f"{settings.SUPABASE_URL}/auth/v1/user"
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    url,
                    headers={
                        "apikey": settings.SUPABASE_ANON_KEY,
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    }
                )
            
            if response.status_code == 200:
                # Session is valid
                user_data = response.json()
                returned_user_id = user_data.get("id")
                
                # Verify the user ID matches
                if returned_user_id != user_id:
                    logger.warning(
                        f"User ID mismatch: token claimed {user_id}, "
                        f"Supabase returned {returned_user_id}"
                    )
                    return False
                
                logger.debug(f"Session verified as active for user: {user_id}")
                return True
            
            elif response.status_code == 401:
                # Token is invalid or revoked in Supabase
                logger.info(f"Session invalid/revoked for user: {user_id}")
                return False
            
            else:
                # Unexpected response
                logger.warning(
                    f"Unexpected response from Supabase session verification: "
                    f"Status {response.status_code}"
                )
                # In case of server errors, we could fall back to Option B
                # For now, we'll reject the request for security
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Session verification unavailable"
                )
        
        except httpx.RequestError as e:
            logger.error(f"Error verifying session with Supabase: {str(e)}")
            # If Supabase is unavailable, reject for security
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Session verification service unavailable"
            )
    
    @staticmethod
    def validate_session(access_token: str, user_id: str) -> bool:
        """
        Main entry point for session validation.
        
        Args:
            access_token: The JWT access token
            user_id: The user ID to verify
            
        Returns:
            bool: True if session is valid and active
            
        Raises:
            HTTPException: If session is invalid or verification fails
        """
        if not SessionValidator.verify_session_active(access_token, user_id):
            logger.warning(f"Session validation failed for user: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session is invalid or has been revoked"
            )
        
        return True


class TokenRevocationManager:
    """
    Manages token revocation (Option B fallback).
    
    If Supabase session verification is not available,
    this provides a database-backed revocation list.
    
    Used for:
    - Explicit token revocation on logout
    - Emergency revocation of compromised tokens
    - Fallback when Supabase API is unavailable
    """
    
    @staticmethod
    def revoke_token(access_token: str, user_id: str, jti: Optional[str] = None) -> bool:
        """
        Revoke a token by adding it to the revocation list.
        
        Args:
            access_token: The JWT access token to revoke
            user_id: The user ID
            jti: JWT ID claim (for token identification)
            
        Returns:
            bool: True if revocation successful
        """
        try:
            # Extract JTI from token if not provided
            if not jti:
                import jwt
                try:
                    decoded = jwt.decode(
                        access_token,
                        options={"verify_signature": False}
                    )
                    jti = decoded.get("jti", access_token[:32])
                except:
                    jti = access_token[:32]
            
            # Add token to revocation list
            result = SupabaseClient.revoke_token(
                user_id=user_id,
                jti=jti,
                token_hash=hash(access_token)
            )
            
            logger.info(f"Token revoked for user: {user_id}")
            return result
        
        except Exception as e:
            logger.error(f"Error revoking token: {str(e)}")
            return False
    
    @staticmethod
    def is_token_revoked(jti: str, user_id: Optional[str] = None) -> bool:
        """
        Check if a token is in the revocation list.
        
        Args:
            jti: The JWT ID claim
            user_id: Optional user ID for more specific lookup
            
        Returns:
            bool: True if token is revoked
        """
        try:
            result = SupabaseClient.check_revoked_token(jti, user_id)
            if result:
                logger.info(f"Token revocation found for jti: {jti}")
            return result
        
        except Exception as e:
            logger.error(f"Error checking token revocation: {str(e)}")
            # Default to secure behavior - reject if we can't verify
            return True
    
    @staticmethod
    def cleanup_expired_revocations(days_old: int = 30) -> int:
        """
        Clean up expired revocations from the database.
        
        Args:
            days_old: Remove revocations older than this many days
            
        Returns:
            int: Number of revocations cleaned up
        """
        try:
            count = SupabaseClient.cleanup_revoked_tokens(days_old)
            logger.info(f"Cleaned up {count} expired token revocations")
            return count
        except Exception as e:
            logger.error(f"Error cleaning up revocations: {str(e)}")
            return 0
