"""
Unit tests for JWT validation using Supabase JWKS.
Tests signature validation, expiration, issuer validation, etc.
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import jwt
from fastapi import HTTPException, status

from app.core.jwt_validator import SupabaseJWTValidator, JWKSCache


@pytest.fixture
def mock_jwks():
    """Mock JWKS response from Supabase."""
    return {
        "keys": [
            {
                "kid": "test-key-id-1",
                "kty": "RSA",
                "use": "sig",
                "n": "test-n-value",
                "e": "AQAB"
            }
        ]
    }


@pytest.fixture
def mock_config(monkeypatch):
    """Mock configuration."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("SESSION_VALIDATION_ENABLED", "true")


class TestJWKSCache:
    """Test JWKS caching functionality."""
    
    def test_jwks_cache_initialization(self):
        """Test JWKS cache can be created."""
        cache = JWKSCache()
        assert cache is not None
    
    def test_cache_is_singleton(self):
        """Test JWKS cache is a singleton."""
        cache1 = JWKSCache()
        cache2 = JWKSCache()
        assert cache1 is cache2
    
    def test_invalidate_cache(self):
        """Test cache invalidation."""
        JWKSCache._cache = {"test": "data"}
        JWKSCache.invalidate()
        assert JWKSCache._cache == {}


class TestSupabaseJWTValidator:
    """Test Supabase JWT validation."""
    
    def test_get_signing_key_missing_kid(self):
        """Test error when token missing key ID in header."""
        with patch("jwt.get_unverified_header", return_value={}):
            with pytest.raises(HTTPException) as exc_info:
                SupabaseJWTValidator.get_signing_key("invalid-token")
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "key ID" in exc_info.value.detail
    
    def test_get_signing_key_malformed_token(self):
        """Test error with malformed token."""
        with patch("jwt.get_unverified_header", side_effect=jwt.DecodeError("bad")):
            with pytest.raises(HTTPException) as exc_info:
                SupabaseJWTValidator.get_signing_key("malformed")
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "malformed" in exc_info.value.detail.lower()
    
    def test_validate_token_expired(self):
        """Test validation fails for expired token."""
        with patch.object(SupabaseJWTValidator, "get_signing_key", return_value={}):
            with patch("jwt.decode", side_effect=jwt.ExpiredSignatureError()):
                with pytest.raises(HTTPException) as exc_info:
                    SupabaseJWTValidator.validate_token("expired-token")
                
                assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
                assert "expired" in exc_info.value.detail.lower()
    
    def test_validate_token_invalid_signature(self):
        """Test validation fails for tampered token."""
        with patch.object(SupabaseJWTValidator, "get_signing_key", return_value={}):
            with patch("jwt.decode", side_effect=jwt.InvalidSignatureError()):
                with pytest.raises(HTTPException) as exc_info:
                    SupabaseJWTValidator.validate_token("tampered-token")
                
                assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
                assert "signature" in exc_info.value.detail.lower()
    
    def test_validate_token_invalid_issuer(self):
        """Test validation fails for wrong issuer."""
        with patch.object(SupabaseJWTValidator, "get_signing_key", return_value={}):
            with patch("jwt.decode", side_effect=jwt.InvalidIssuerError()):
                with pytest.raises(HTTPException) as exc_info:
                    SupabaseJWTValidator.validate_token("wrong-issuer-token")
                
                assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
                assert "issuer" in exc_info.value.detail.lower()
    
    def test_extract_user_id_missing_sub(self):
        """Test error when sub claim is missing."""
        with patch.object(
            SupabaseJWTValidator, 
            "validate_token", 
            return_value={"exp": 9999999999}
        ):
            with pytest.raises(HTTPException) as exc_info:
                SupabaseJWTValidator.extract_user_id("token-without-sub")
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "user ID" in exc_info.value.detail
    
    def test_extract_user_id_success(self):
        """Test successful user ID extraction."""
        test_user_id = "123e4567-e89b-12d3-a456-426614174000"
        with patch.object(
            SupabaseJWTValidator,
            "validate_token",
            return_value={"sub": test_user_id, "exp": 9999999999}
        ):
            user_id = SupabaseJWTValidator.extract_user_id("valid-token")
            assert user_id == test_user_id
    
    def test_extract_email_missing_email(self):
        """Test error when email claim is missing."""
        with patch.object(
            SupabaseJWTValidator,
            "validate_token",
            return_value={"sub": "123"}
        ):
            with pytest.raises(HTTPException) as exc_info:
                SupabaseJWTValidator.extract_email("token-without-email")
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "email" in exc_info.value.detail
    
    def test_extract_email_success(self):
        """Test successful email extraction."""
        test_email = "user@example.com"
        with patch.object(
            SupabaseJWTValidator,
            "validate_token",
            return_value={"sub": "123", "email": test_email}
        ):
            email = SupabaseJWTValidator.extract_email("valid-token")
            assert email == test_email
    
    def test_get_token_claims_success(self):
        """Test successful token claims retrieval."""
        claims = {
            "sub": "user-123",
            "email": "user@example.com",
            "iat": 1234567890,
            "exp": 9999999999,
            "iss": "https://test.supabase.co/auth/v1"
        }
        with patch.object(
            SupabaseJWTValidator,
            "validate_token",
            return_value=claims
        ):
            result = SupabaseJWTValidator.get_token_claims("valid-token")
            assert result == claims


class TestJWTValidationScenarios:
    """Test realistic JWT validation scenarios."""
    
    def test_valid_ceo_token(self):
        """Test validation of valid CEO token."""
        ceo_claims = {
            "sub": "ceo-uuid",
            "email": "ceo@company.com",
            "aud": ["authenticated"],
            "iss": "https://test.supabase.co/auth/v1",
            "iat": int(datetime.utcnow().timestamp()),
            "exp": int((datetime.utcnow() + timedelta(hours=24)).timestamp())
        }
        
        with patch.object(
            SupabaseJWTValidator,
            "validate_token",
            return_value=ceo_claims
        ):
            result = SupabaseJWTValidator.get_token_claims("ceo-token")
            assert result["sub"] == "ceo-uuid"
            assert result["email"] == "ceo@company.com"
    
    def test_valid_employee_token(self):
        """Test validation of valid Employee token."""
        emp_claims = {
            "sub": "emp-uuid",
            "email": "emp@company.com",
            "aud": ["authenticated"],
            "iss": "https://test.supabase.co/auth/v1",
            "iat": int(datetime.utcnow().timestamp()),
            "exp": int((datetime.utcnow() + timedelta(hours=24)).timestamp())
        }
        
        with patch.object(
            SupabaseJWTValidator,
            "validate_token",
            return_value=emp_claims
        ):
            result = SupabaseJWTValidator.get_token_claims("emp-token")
            assert result["sub"] == "emp-uuid"
            assert result["email"] == "emp@company.com"
    
    def test_token_with_custom_claims(self):
        """Test token with custom claims is validated."""
        claims_with_extras = {
            "sub": "user-123",
            "email": "user@company.com",
            "custom_claim": "custom-value",
            "iat": int(datetime.utcnow().timestamp()),
            "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp())
        }
        
        with patch.object(
            SupabaseJWTValidator,
            "validate_token",
            return_value=claims_with_extras
        ):
            result = SupabaseJWTValidator.get_token_claims("custom-token")
            assert result.get("custom_claim") == "custom-value"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
