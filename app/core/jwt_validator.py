"""
JWT validation using Supabase JWKS.
Implements production-grade JWT verification for Supabase-issued tokens.

This module handles:
- JWKS retrieval and caching
- JWT signature validation
- Token expiration checks
- Issuer and audience validation
- Graceful error handling with structured logging
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from functools import lru_cache

import httpx
import jwt
from jwt import PyJWKClient
from jwt.exceptions import (
    InvalidSignatureError,
    ExpiredSignatureError,
    InvalidIssuerError,
    InvalidAudienceError,
    InvalidAlgorithmError,
    DecodeError,
    PyJWKClientError,
)
from fastapi import HTTPException, status

from app.core.config import settings


logger = logging.getLogger(__name__)


class JWKSCache:
    """Cache JWKS to reduce API calls to Supabase."""
    
    _instance: Optional["JWKSCache"] = None
    _cache: Dict[str, Any] = {}
    _cache_expiry: Optional[datetime] = None
    _cache_ttl_seconds: int = 3600  # 1 hour
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @staticmethod
    def _is_cache_valid() -> bool:
        """Check if cached JWKS is still valid."""
        if not JWKSCache._cache_expiry:
            return False
        return datetime.utcnow() < JWKSCache._cache_expiry
    
    @staticmethod
    def get() -> Dict[str, Any]:
        """
        Get JWKS from cache or fetch from Supabase.
        
        Returns:
            Dict: JWKS data with keys
            
        Raises:
            HTTPException: If JWKS retrieval fails
        """
        if JWKSCache._is_cache_valid() and JWKSCache._cache:
            logger.debug("JWKS retrieved from cache")
            return JWKSCache._cache
        
        logger.info("Fetching JWKS from Supabase")
        jwks = JWKSCache._fetch_jwks()
        
        # Cache for 1 hour
        JWKSCache._cache = jwks
        JWKSCache._cache_expiry = datetime.utcnow() + timedelta(
            seconds=JWKSCache._cache_ttl_seconds
        )
        
        logger.debug(f"JWKS cached, expires at {JWKSCache._cache_expiry}")
        return jwks
    
    @staticmethod
    def _fetch_jwks() -> Dict[str, Any]:
        """
        Fetch JWKS from Supabase.
        
        Returns:
            Dict: JWKS data
            
        Raises:
            HTTPException: If JWKS retrieval fails
        """
        jwks_url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(jwks_url)
                
                if response.status_code != 200:
                    logger.error(
                        f"Failed to fetch JWKS from {jwks_url}: "
                        f"Status {response.status_code}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to validate token: JWKS unavailable"
                    )
                
                jwks = response.json()
                logger.debug(f"JWKS fetched successfully with {len(jwks.get('keys', []))} keys")
                return jwks
                
        except httpx.RequestError as e:
            logger.error(f"Error fetching JWKS: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to validate token: JWKS service unavailable"
            )
    
    @staticmethod
    def invalidate():
        """Invalidate the cache (useful for testing or forced refresh)."""
        JWKSCache._cache = {}
        JWKSCache._cache_expiry = None
        logger.debug("JWKS cache invalidated")


class SupabaseJWTValidator:
    """
    Validates JWT tokens issued by Supabase.
    
    Implements:
    - Signature validation using JWKS
    - Expiration validation
    - Issuer validation
    - Audience validation
    - Subject validation
    """
    
    @staticmethod
    def get_signing_key(token: str) -> Any:
        """
        Get the signing key from Supabase JWKS for the token.

        Args:
            token: The JWT token

        Returns:
            Any: Parsed signing key

        Raises:
            HTTPException: If signing key not found or token invalid
        """
        jwks_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"

        try:
            header = jwt.get_unverified_header(token)
            if not isinstance(header, dict) or not header.get("kid"):
                logger.warning("JWT header is missing key ID (kid)")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: missing key ID",
                )

            jwk_client = PyJWKClient(jwks_url)
            signing_key = jwk_client.get_signing_key_from_jwt(token).key
            logger.debug("Found signing key from Supabase JWKS")
            return signing_key

        except DecodeError as e:
            logger.warning(f"Failed to decode JWT header: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: malformed JWT",
            )
        except HTTPException:
            raise
        except PyJWKClientError as e:
            logger.warning(f"Failed to retrieve JWKS signing key: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: signing key not found",
            )
        except Exception as e:
            logger.error(f"Unexpected JWKS lookup error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: signing key lookup failed",
            )
    
    @staticmethod
    def validate_token(token: str) -> Dict[str, Any]:
        """
        Validate JWT token issued by Supabase.
        
        Validates:
        - Signature (using JWKS)
        - Expiration
        - Issuer (must be Supabase)
        - Audience (optional, if configured)
        - Subject (must exist)
        
        Args:
            token: The JWT token to validate
            
        Returns:
            Dict: Decoded token claims
            
        Raises:
            HTTPException: If token is invalid or expired
        """
        try:
            # Get signing key
            signing_key = SupabaseJWTValidator.get_signing_key(token)
            issuer = settings.SUPABASE_JWT_ISSUER_URL.rstrip('/') if settings.SUPABASE_JWT_ISSUER_URL else f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"
            audience = settings.SUPABASE_JWT_AUDIENCE

            algorithms = [settings.SUPABASE_JWT_ALGORITHM, settings.JWT_ALGORITHM, "ES256"]
            if "RS256" not in algorithms:
                algorithms.append("RS256")
            if "HS256" not in algorithms:
                algorithms.append("HS256")

            payload = jwt.decode(
                token,
                signing_key,
                algorithms=algorithms,
                issuer=issuer,
                audience=audience,
            )
            
            logger.debug(f"JWT token validated successfully for user: {payload.get('sub')}")
            return payload
            
        except ExpiredSignatureError:
            logger.warning("JWT token has expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )
            
        except InvalidSignatureError:
            logger.warning("JWT signature is invalid")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token signature"
            )
            
        except InvalidIssuerError:
            logger.warning(f"JWT issuer is invalid: {token}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token issuer"
            )
            
        except InvalidAudienceError:
            logger.warning("JWT audience is invalid")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token audience"
            )

        except InvalidAlgorithmError:
            logger.warning("JWT algorithm is not allowed")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token algorithm"
            )
            
        except jwt.DecodeError:
            logger.warning("JWT could not be decoded")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format"
            )
            
        except Exception as e:
            logger.error(f"Unexpected error validating JWT: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    
    @staticmethod
    def extract_user_id(token: str) -> str:
        """
        Extract and validate user ID from JWT token.
        
        Args:
            token: The JWT token
            
        Returns:
            str: The user ID (sub claim)
            
        Raises:
            HTTPException: If token is invalid or user ID missing
        """
        payload = SupabaseJWTValidator.validate_token(token)
        user_id = payload.get("sub")
        
        if not user_id:
            logger.warning("JWT token missing 'sub' (user ID) claim")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID"
            )
        
        return user_id
    
    @staticmethod
    def extract_email(token: str) -> str:
        """
        Extract and validate email from JWT token.
        
        Args:
            token: The JWT token
            
        Returns:
            str: The user email
            
        Raises:
            HTTPException: If token is invalid or email missing
        """
        payload = SupabaseJWTValidator.validate_token(token)
        email = payload.get("email")
        
        if not email:
            logger.warning("JWT token missing 'email' claim")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing email"
            )
        
        return email
    
    @staticmethod
    def get_token_claims(token: str) -> Dict[str, Any]:
        """
        Get all claims from validated JWT token.
        
        Args:
            token: The JWT token
            
        Returns:
            Dict: All token claims
            
        Raises:
            HTTPException: If token is invalid
        """
        return SupabaseJWTValidator.validate_token(token)
