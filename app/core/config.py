"""
Core configuration for the FastAPI application.
Loads environment variables and provides configuration for Supabase and JWT.
"""

import os
from typing import List, Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
load_dotenv(os.path.join(BASE_DIR, '.env'))
load_dotenv(os.path.join(BASE_DIR, '.env.local'), override=True)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Supabase Configuration
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    
    # JWT Configuration
    JWT_SECRET: str = ""  # No longer used for access token validation
    JWT_ALGORITHM: str = "HS256"  # Keep for reference, Supabase uses RS256
    JWT_EXPIRATION_HOURS: int = 24
    
    # Supabase JWT Configuration
    SUPABASE_JWT_ALGORITHM: str = "RS256"
    SUPABASE_JWT_AUDIENCE: str = "authenticated"
    SUPABASE_JWT_ISSUER_URL: str = ""  # Will be set from SUPABASE_URL

    # Session Validation Configuration
    SESSION_VALIDATION_ENABLED: bool = True
    JWKS_CACHE_TTL_SECONDS: int = 3600  # 1 hour
    TOKEN_REVOCATION_ENABLED: bool = True
    
    # API Configuration
    API_V1_STR: str = "/api"
    PROJECT_NAME: str = "Attendance Dashboard API"
    DEBUG: bool = False

    # Resend Configuration
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = ""

    # Scheduled job protection (optional; leave empty to allow unauthenticated job calls)
    SCHEDULED_JOB_TOKEN: str = ""
    MINERVA_SYNC_MAX_WORKERS: int = 4
    
    # Minerva Attendance API Configuration
    MINERVA_BASE_URL: str
    MINERVA_API_TOKEN: str
    MINERVA_EMPLOYEE_ENDPOINT: str
    MINERVA_TRANSACTION_ENDPOINT: str

    # CORS Configuration
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    class Config:
        """Pydantic config."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
