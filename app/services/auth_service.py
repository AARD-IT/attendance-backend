"""
Authentication service layer.
Handles user authentication logic with clean Supabase integration.
"""

import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException, status

from app.db.supabase import SupabaseClient
from app.models.profile import Profile
from app.services.token_service import token_service

logger = logging.getLogger(__name__)


class AuthService:
    """Service responsible for login, signup, profile lookup, and logout."""

    @staticmethod
    def _extract_access_token(auth_response: Dict[str, Any]) -> Optional[str]:
        session = auth_response.get('session')
        if isinstance(session, dict):
            token = session.get('access_token')
            if token:
                return token
        return auth_response.get('access_token')

    @staticmethod
    def login(email: str, password: str) -> Dict[str, Any]:
        """Authenticate user using Supabase email/password login."""
        logger.info(f"Login attempt for email={email}")

        auth_response = SupabaseClient.sign_in_with_password(email, password)
        user_data = auth_response.get('user')
        access_token = AuthService._extract_access_token(auth_response)

        if not user_data or not access_token:
            logger.warning(f"Login failed for email={email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Invalid email or password'
            )

        user_id = user_data.get('id')
        if not user_id:
            logger.error('Authenticated user missing id claim')
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Authentication response missing user id'
            )

        profile_data = SupabaseClient.fetch_profile_by_id(user_id)
        if not profile_data:
            logger.warning(f"Profile not found for user_id={user_id}, attempting to create missing profile")
            try:
                user_email = user_data.get('email', email)
                profile_data = SupabaseClient.create_profile(
                    user_id=user_id,
                    email=user_email,
                    role='EMPLOYEE',
                    full_name=user_email.split('@')[0]
                )
                logger.info(f"Created missing profile for user_id={user_id} email={user_email}")
            except Exception as profile_error:
                logger.error(f"Failed to create missing profile for user_id={user_id}: {str(profile_error)}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail='User profile not found'
                )

        profile = Profile(**profile_data)
        return {
            'user': {
                'id': profile.id,
                'email': profile.email,
                'role': profile.role,
                'full_name': profile.full_name,
            },
            'role': profile.role,
            'access_token': access_token,
        }

    @staticmethod
    def signup(email: str, password: str, full_name: str, role: str) -> Dict[str, Any]:
        """Register a new Supabase auth user and create a matching profile."""
        logger.info(f"Signup attempt for email={email}")

        existing_profile = SupabaseClient.fetch_profile_by_email(email)
        if existing_profile:
            logger.warning(f"Signup conflict for email={email}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='A user with this email already exists. Please log in instead.'
            )

        created_user_id: Optional[str] = None
        try:
            user_data = SupabaseClient.create_user(email, password)
            created_user_id = user_data.get('id')

            if not created_user_id:
                logger.error(f"Supabase returned empty user id for email={email}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail='Unable to create user'
                )

            if email.strip().lower() == 'sheriffrafiq71@gmail.com':
                role = 'CEO'

            profile_data = SupabaseClient.create_profile(created_user_id, email, role, full_name)
            profile = Profile(**profile_data) if profile_data else Profile(
                id=created_user_id,
                email=email,
                role=role,
                full_name=full_name,
            )

            try:
                login_response = SupabaseClient.sign_in_with_password(email, password)
                access_token = AuthService._extract_access_token(login_response)
            except HTTPException as exc:
                logger.error(f"Signup succeeded but automatic login failed for email={email}: {exc.detail}")
                return {
                    'user': {
                        'id': profile.id,
                        'email': profile.email,
                        'role': profile.role,
                        'full_name': profile.full_name,
                    },
                    'role': profile.role,
                    'access_token': None,
                }

            if not access_token:
                logger.error(f"Signup succeeded but login returned no access token for email={email}")
                return {
                    'user': {
                        'id': profile.id,
                        'email': profile.email,
                        'role': profile.role,
                        'full_name': profile.full_name,
                    },
                    'role': profile.role,
                    'access_token': None,
                }

            logger.info(f"User registered and signed in successfully email={email} user_id={created_user_id}")
            return {
                'user': {
                    'id': profile.id,
                    'email': profile.email,
                    'role': profile.role,
                    'full_name': profile.full_name,
                },
                'role': profile.role,
                'access_token': access_token,
            }

        except HTTPException as exc:
            if created_user_id:
                SupabaseClient.delete_user(created_user_id)
            raise
        except Exception as exc:
            if created_user_id:
                SupabaseClient.delete_user(created_user_id)
            error_str = str(exc).lower()
            if 'email' in error_str and ('exist' in error_str or 'duplicate' in error_str or 'already' in error_str):
                logger.warning(f"Email already exists in auth for email={email}, user should login instead")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail='A user with this email already exists. Please log in instead.'
                )
            logger.error(f"Signup error email={email}: {str(exc)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Signup failed. Please try again.'
            )

    @staticmethod
    def get_profile(user_id: str) -> Optional[Profile]:
        try:
            profile_data = SupabaseClient.fetch_profile_by_id(user_id)
            return Profile(**profile_data) if profile_data else None
        except Exception as exc:
            logger.error(f"Profile lookup failed user_id={user_id}: {str(exc)}")
            return None

    @staticmethod
    def get_profile_by_email(email: str) -> Optional[Profile]:
        try:
            profile_data = SupabaseClient.fetch_profile_by_email(email)
            return Profile(**profile_data) if profile_data else None
        except Exception as exc:
            logger.error(f"Profile lookup by email failed email={email}: {str(exc)}")
            return None

    @staticmethod
    def logout(access_token: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        logger.info(f"Logout initiated user_id={user_id}")

        try:
            if user_id:
                token_service.revoke_token(access_token, user_id)

            logout_result = SupabaseClient.sign_out(access_token)
            logger.debug(f"Supabase logout result: {logout_result}")
            return {'success': True, 'message': 'Logged out successfully'}

        except Exception as exc:
            logger.error(f"Logout error user_id={user_id}: {str(exc)}")
            return {'success': True, 'message': 'Logged out'}


# Create global auth service instance
auth_service = AuthService()

