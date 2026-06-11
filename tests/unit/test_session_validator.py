"""
Unit tests for session validation and token revocation.
Tests session verification and revocation management.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException, status
import httpx

from app.core.session_validator import SessionValidator, TokenRevocationManager
from app.db.supabase import SupabaseClient


@pytest.fixture
def mock_config(monkeypatch):
    """Mock configuration."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")


class TestSessionValidator:
    """Test session validation."""
    
    @patch("httpx.Client.get")
    def test_verify_session_active_success(self, mock_get):
        """Test successful session verification."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "user-123"}
        mock_get.return_value = mock_response
        
        result = SessionValidator.verify_session_active("valid-token", "user-123")
        assert result is True
    
    @patch("httpx.Client.get")
    def test_verify_session_invalid_token(self, mock_get):
        """Test session verification fails for invalid token."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response
        
        result = SessionValidator.verify_session_active("invalid-token", "user-123")
        assert result is False
    
    @patch("httpx.Client.get")
    def test_verify_session_user_id_mismatch(self, mock_get):
        """Test session verification fails when user ID doesn't match."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "different-user"}
        mock_get.return_value = mock_response
        
        result = SessionValidator.verify_session_active("token", "user-123")
        assert result is False
    
    @patch("httpx.Client.get")
    def test_verify_session_network_error(self, mock_get):
        """Test session verification fails on network error."""
        mock_get.side_effect = httpx.RequestError("Connection failed")
        
        with pytest.raises(HTTPException) as exc_info:
            SessionValidator.verify_session_active("token", "user-123")
        
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    
    @patch("httpx.Client.get")
    def test_verify_session_unexpected_response(self, mock_get):
        """Test session verification fails on unexpected response."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response
        
        with pytest.raises(HTTPException) as exc_info:
            SessionValidator.verify_session_active("token", "user-123")
        
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    
    @patch("httpx.Client.get")
    def test_validate_session_success(self, mock_get):
        """Test validate_session succeeds for active session."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "user-123"}
        mock_get.return_value = mock_response
        
        result = SessionValidator.validate_session("valid-token", "user-123")
        assert result is True
    
    @patch("httpx.Client.get")
    def test_validate_session_revoked(self, mock_get):
        """Test validate_session fails for revoked session."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response
        
        with pytest.raises(HTTPException) as exc_info:
            SessionValidator.validate_session("revoked-token", "user-123")
        
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "revoked" in exc_info.value.detail.lower()


class TestTokenRevocationManager:
    """Test token revocation management."""
    
    @patch.object(SupabaseClient, "revoke_token")
    def test_revoke_token_success(self, mock_revoke):
        """Test token revocation succeeds."""
        mock_revoke.return_value = True
        
        result = TokenRevocationManager.revoke_token(
            "token-to-revoke",
            "user-123",
            "jti-value"
        )
        
        assert result is True
        mock_revoke.assert_called_once()
    
    @patch.object(SupabaseClient, "revoke_token")
    def test_revoke_token_failure(self, mock_revoke):
        """Test token revocation failure."""
        mock_revoke.return_value = False
        
        result = TokenRevocationManager.revoke_token(
            "token-to-revoke",
            "user-123",
            "jti-value"
        )
        
        assert result is False
    
    @patch.object(SupabaseClient, "check_revoked_token")
    def test_is_token_revoked_true(self, mock_check):
        """Test token revocation check returns True for revoked token."""
        mock_check.return_value = True
        
        result = TokenRevocationManager.is_token_revoked("jti-value", "user-123")
        assert result is True
    
    @patch.object(SupabaseClient, "check_revoked_token")
    def test_is_token_revoked_false(self, mock_check):
        """Test token revocation check returns False for valid token."""
        mock_check.return_value = False
        
        result = TokenRevocationManager.is_token_revoked("jti-value", "user-123")
        assert result is False
    
    @patch.object(SupabaseClient, "check_revoked_token")
    def test_is_token_revoked_error_defaults_to_true(self, mock_check):
        """Test revocation check defaults to True on error (secure default)."""
        mock_check.side_effect = Exception("Database error")
        
        result = TokenRevocationManager.is_token_revoked("jti-value")
        assert result is True
    
    @patch.object(SupabaseClient, "cleanup_revoked_tokens")
    def test_cleanup_expired_revocations(self, mock_cleanup):
        """Test cleanup of expired revocations."""
        mock_cleanup.return_value = 10
        
        result = TokenRevocationManager.cleanup_expired_revocations(30)
        assert result == 10
    
    @patch.object(SupabaseClient, "cleanup_revoked_tokens")
    def test_cleanup_error_returns_zero(self, mock_cleanup):
        """Test cleanup returns 0 on error."""
        mock_cleanup.side_effect = Exception("Database error")
        
        result = TokenRevocationManager.cleanup_expired_revocations()
        assert result == 0


class TestRevocationScenarios:
    """Test realistic revocation scenarios."""
    
    @patch.object(SupabaseClient, "revoke_token")
    def test_logout_revokes_token(self, mock_revoke):
        """Test logout revokes the user's token."""
        mock_revoke.return_value = True
        
        result = TokenRevocationManager.revoke_token(
            access_token="token-abc123",
            user_id="user-uuid",
            jti="jti-value"
        )
        
        assert result is True
    
    @patch.object(SupabaseClient, "check_revoked_token")
    def test_subsequent_request_with_revoked_token_fails(self, mock_check):
        """Test that revoked tokens are rejected on subsequent requests."""
        mock_check.return_value = True
        
        is_revoked = TokenRevocationManager.is_token_revoked("jti-value")
        assert is_revoked is True
    
    @patch.object(SupabaseClient, "revoke_token")
    @patch.object(SupabaseClient, "check_revoked_token")
    def test_revocation_flow(self, mock_check, mock_revoke):
        """Test complete revocation flow."""
        # 1. Initial token is not revoked
        mock_check.return_value = False
        assert TokenRevocationManager.is_token_revoked("jti-1") is False
        
        # 2. Revoke the token
        mock_revoke.return_value = True
        assert TokenRevocationManager.revoke_token("token", "user", "jti-1") is True
        
        # 3. Token is now revoked
        mock_check.return_value = True
        assert TokenRevocationManager.is_token_revoked("jti-1") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
