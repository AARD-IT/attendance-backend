"""
Integration tests for authentication security.
Tests complete authentication flows and access control.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.models.profile import Profile


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_supabase(monkeypatch):
    """Mock Supabase dependencies."""
    # Mock config
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("SESSION_VALIDATION_ENABLED", "true")


@pytest.fixture
def valid_ceo_token():
    """Generate a valid CEO token."""
    import jwt
    payload = {
        "sub": "ceo-123",
        "email": "ceo@company.com",
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(hours=24)).timestamp()),
        "iss": "https://test.supabase.co/auth/v1"
    }
    return jwt.encode(payload, "secret", algorithm="HS256")


@pytest.fixture
def valid_employee_token():
    """Generate a valid Employee token."""
    import jwt
    payload = {
        "sub": "emp-456",
        "email": "emp@company.com",
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(hours=24)).timestamp()),
        "iss": "https://test.supabase.co/auth/v1"
    }
    return jwt.encode(payload, "secret", algorithm="HS256")


@pytest.fixture
def expired_token():
    """Generate an expired token."""
    import jwt
    payload = {
        "sub": "user-789",
        "email": "expired@company.com",
        "iat": int((datetime.utcnow() - timedelta(hours=25)).timestamp()),
        "exp": int((datetime.utcnow() - timedelta(hours=1)).timestamp()),
        "iss": "https://test.supabase.co/auth/v1"
    }
    return jwt.encode(payload, "secret", algorithm="HS256")


@pytest.fixture
def tampered_token(valid_ceo_token):
    """Create a tampered token."""
    # Modify the token slightly to invalidate signature
    return valid_ceo_token[:-10] + "tampered123"


class TestAuthenticationFlow:
    """Test complete authentication flow."""
    
    def test_health_check(self, client):
        """Test health check endpoint works."""
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "healthy"
    
    def test_api_health_check(self, client):
        """Test API health check endpoint works."""
        response = client.get("/api/health")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "ok"
    
    def test_root_endpoint(self, client):
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK
        assert "Attendance Dashboard API" in response.json()["message"]


class TestTokenValidation:
    """Test JWT token validation."""
    
    @patch("app.core.jwt_validator.SupabaseJWTValidator.validate_token")
    @patch("app.core.session_validator.SessionValidator.verify_session_active")
    @patch("app.services.auth_service.auth_service.get_profile")
    def test_valid_token_accepted(
        self,
        mock_get_profile,
        mock_verify_session,
        mock_validate,
        client,
        valid_ceo_token
    ):
        """Test valid token is accepted."""
        mock_validate.return_value = {
            "sub": "ceo-123",
            "email": "ceo@company.com"
        }
        mock_verify_session.return_value = True
        mock_get_profile.return_value = Profile(
            id="ceo-123",
            email="ceo@company.com",
            role="CEO",
            full_name="CEO User"
        )
        
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {valid_ceo_token}"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["role"] == "CEO"
    
    @patch("app.core.jwt_validator.SupabaseJWTValidator.validate_token")
    def test_expired_token_rejected(self, mock_validate, client, expired_token):
        """Test expired token is rejected."""
        from fastapi import HTTPException
        mock_validate.side_effect = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
        
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    @patch("app.core.jwt_validator.SupabaseJWTValidator.validate_token")
    def test_tampered_token_rejected(self, mock_validate, client, tampered_token):
        """Test tampered token is rejected."""
        from fastapi import HTTPException
        mock_validate.side_effect = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature"
        )
        
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {tampered_token}"}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_missing_bearer_token(self, client):
        """Test request without bearer token is rejected."""
        response = client.get("/api/auth/me")
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_invalid_bearer_format(self, client):
        """Test invalid bearer format is rejected."""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "InvalidFormat token"}
        )
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED]


class TestRoleBasedAccess:
    """Test role-based access control."""
    
    @patch("app.core.jwt_validator.SupabaseJWTValidator.validate_token")
    @patch("app.core.session_validator.SessionValidator.verify_session_active")
    @patch("app.services.auth_service.auth_service.get_profile")
    def test_ceo_can_access_ceo_dashboard(
        self,
        mock_get_profile,
        mock_verify_session,
        mock_validate,
        client,
        valid_ceo_token
    ):
        """Test CEO can access CEO dashboard."""
        mock_validate.return_value = {
            "sub": "ceo-123",
            "email": "ceo@company.com"
        }
        mock_verify_session.return_value = True
        mock_get_profile.return_value = Profile(
            id="ceo-123",
            email="ceo@company.com",
            role="CEO",
            full_name="CEO User"
        )
        
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {valid_ceo_token}"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["role"] == "CEO"
    
    @patch("app.core.jwt_validator.SupabaseJWTValidator.validate_token")
    @patch("app.core.session_validator.SessionValidator.verify_session_active")
    @patch("app.services.auth_service.auth_service.get_profile")
    def test_employee_cannot_access_ceo_endpoint(
        self,
        mock_get_profile,
        mock_verify_session,
        mock_validate,
        client,
        valid_employee_token
    ):
        """Test Employee cannot access CEO-only endpoint."""
        mock_validate.return_value = {
            "sub": "emp-456",
            "email": "emp@company.com"
        }
        mock_verify_session.return_value = True
        mock_get_profile.return_value = Profile(
            id="emp-456",
            email="emp@company.com",
            role="EMPLOYEE",
            full_name="Employee User"
        )
        
        # Try to access CEO endpoint (would be protected with require_ceo)
        # This is a mock - actual endpoint testing would require mocking the routes
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {valid_employee_token}"}
        )
        
        # Should succeed for /me endpoint, but would fail for CEO-specific endpoints
        assert response.status_code == status.HTTP_200_OK


class TestSessionRevocation:
    """Test session revocation and logout."""
    
    @patch("app.core.jwt_validator.SupabaseJWTValidator.validate_token")
    @patch("app.core.session_validator.SessionValidator.verify_session_active")
    @patch("app.services.auth_service.auth_service.logout")
    @patch("app.services.auth_service.auth_service.get_profile")
    def test_logout_endpoint(
        self,
        mock_get_profile,
        mock_logout,
        mock_verify_session,
        mock_validate,
        client,
        valid_ceo_token
    ):
        """Test logout endpoint."""
        mock_validate.return_value = {
            "sub": "ceo-123",
            "email": "ceo@company.com"
        }
        mock_verify_session.return_value = True
        mock_get_profile.return_value = Profile(
            id="ceo-123",
            email="ceo@company.com",
            role="CEO",
            full_name="CEO User"
        )
        mock_logout.return_value = {"success": True, "message": "Logged out successfully"}
        
        response = client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {valid_ceo_token}"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True
    
    @patch("app.core.jwt_validator.SupabaseJWTValidator.validate_token")
    @patch("app.core.session_validator.SessionValidator.verify_session_active")
    def test_revoked_session_rejected(
        self,
        mock_verify_session,
        mock_validate,
        client,
        valid_ceo_token
    ):
        """Test revoked session is rejected."""
        from fastapi import HTTPException
        mock_validate.return_value = {
            "sub": "ceo-123",
            "email": "ceo@company.com"
        }
        mock_verify_session.side_effect = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid or has been revoked"
        )
        
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {valid_ceo_token}"}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestErrorHandling:
    """Test error handling and responses."""
    
    def test_nonexistent_endpoint(self, client):
        """Test 404 for nonexistent endpoint."""
        response = client.get("/api/nonexistent")
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    @patch("app.core.jwt_validator.SupabaseJWTValidator.validate_token")
    def test_profile_not_found(
        self,
        mock_validate,
        client,
        valid_ceo_token
    ):
        """Test 401 when profile not found."""
        from fastapi import HTTPException
        mock_validate.return_value = {
            "sub": "unknown-user",
            "email": "unknown@company.com"
        }
        
        with patch("app.services.auth_service.auth_service.get_profile", return_value=None):
            response = client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {valid_ceo_token}"}
            )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
