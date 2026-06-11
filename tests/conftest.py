"""
Pytest configuration and fixtures for Attendance Dashboard tests.
"""

import pytest
import os
from dotenv import load_dotenv
from unittest.mock import MagicMock


# Load environment variables from .env file
load_dotenv()


@pytest.fixture(scope="session")
def test_config():
    """Test configuration fixture."""
    return {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_ANON_KEY": "test-anon-key",
        "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
        "JWT_SECRET": "test-secret",
        "JWT_ALGORITHM": "HS256",
        "SESSION_VALIDATION_ENABLED": "true",
        "JWKS_CACHE_TTL_SECONDS": "3600",
        "TOKEN_REVOCATION_ENABLED": "true"
    }


@pytest.fixture(autouse=True)
def mock_env(test_config, monkeypatch):
    """Automatically mock environment variables for all tests."""
    for key, value in test_config.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def mock_httpx_client(monkeypatch):
    """Mock httpx.Client for all tests."""
    mock_client = MagicMock()
    monkeypatch.setattr("httpx.Client", lambda timeout=None: mock_client)
    return mock_client


@pytest.fixture
def sample_user_id():
    """Sample UUID for testing."""
    return "123e4567-e89b-12d3-a456-426614174000"


@pytest.fixture
def sample_email():
    """Sample email for testing."""
    return "test@example.com"


@pytest.fixture
def sample_ceo_profile(sample_user_id, sample_email):
    """Sample CEO profile for testing."""
    from app.models.profile import Profile
    return Profile(
        id=sample_user_id,
        email=sample_email,
        full_name="Test CEO",
        role="CEO"
    )


@pytest.fixture
def sample_employee_profile(sample_user_id, sample_email):
    """Sample Employee profile for testing."""
    from app.models.profile import Profile
    return Profile(
        id=sample_user_id,
        email=sample_email,
        full_name="Test Employee",
        role="EMPLOYEE"
    )


@pytest.fixture
def sample_jwt_claims(sample_user_id, sample_email):
    """Sample JWT claims for testing."""
    from datetime import datetime, timedelta
    return {
        "sub": sample_user_id,
        "email": sample_email,
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(hours=24)).timestamp()),
        "iss": "https://test.supabase.co/auth/v1",
        "aud": ["authenticated"],
        "jti": "jwt-id-123"
    }


@pytest.fixture
def sample_expired_jwt_claims(sample_user_id, sample_email):
    """Sample expired JWT claims for testing."""
    from datetime import datetime, timedelta
    return {
        "sub": sample_user_id,
        "email": sample_email,
        "iat": int((datetime.utcnow() - timedelta(hours=25)).timestamp()),
        "exp": int((datetime.utcnow() - timedelta(hours=1)).timestamp()),
        "iss": "https://test.supabase.co/auth/v1"
    }


# Mark all tests in tests/unit as unit tests
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "security: Security tests")


@pytest.fixture
def clear_jwks_cache():
    """Clear JWKS cache before and after test."""
    from app.core.jwt_validator import JWKSCache
    JWKSCache.invalidate()
    yield
    JWKSCache.invalidate()
