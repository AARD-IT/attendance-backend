import pytest
from unittest.mock import patch
from fastapi import HTTPException

from app.services.auth_service import AuthService


def test_extract_access_token_from_session():
    auth_response = {
        "session": {"access_token": "session-token"},
        "access_token": "top-level-token"
    }

    assert AuthService._extract_access_token(auth_response) == "session-token"


def test_extract_access_token_top_level():
    auth_response = {"access_token": "top-level-token"}

    assert AuthService._extract_access_token(auth_response) == "top-level-token"


@patch("app.services.auth_service.SupabaseClient.fetch_profile_by_id")
@patch("app.services.auth_service.SupabaseClient.sign_in_with_password")
def test_login_accepts_top_level_access_token(mock_sign_in, mock_fetch_profile):
    mock_sign_in.return_value = {
        "user": {"id": "user-1", "email": "user@example.com"},
        "access_token": "top-level-token"
    }
    mock_fetch_profile.return_value = {
        "id": "user-1",
        "email": "user@example.com",
        "role": "EMPLOYEE",
        "full_name": "Test User"
    }

    result = AuthService.login("user@example.com", "password123")

    assert result["access_token"] == "top-level-token"
    assert result["user"]["id"] == "user-1"
    assert result["user"]["email"] == "user@example.com"
    assert result["user"]["role"] == "EMPLOYEE"


@patch("app.services.auth_service.SupabaseClient.sign_in_with_password")
def test_login_with_invalid_credentials_raises_401(mock_sign_in):
    mock_sign_in.return_value = {"user": None}

    with pytest.raises(HTTPException) as exc_info:
        AuthService.login("user@example.com", "wrongpass")

    assert exc_info.value.status_code == 401
    assert "Invalid email or password" in str(exc_info.value.detail)
