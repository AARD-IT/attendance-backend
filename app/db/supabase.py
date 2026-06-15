"""
Supabase database integration layer.
Handles all communication with Supabase API including authentication and database operations.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import httpx
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


# Supabase API headers for different authentication methods
SUPABASE_HEADERS_ANON = {
    "apikey": settings.SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
}

SUPABASE_HEADERS_SERVICE = {
    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}


class SupabaseClient:
    """Supabase client for database and authentication operations."""
    
    @staticmethod
    def sign_in_with_password(email: str, password: str) -> Dict[str, Any]:
        """
        Sign in user with email and password.
        
        Args:
            email: User email
            password: User password
            
        Returns:
            Dict: Authentication response with access_token and user info
            
        Raises:
            HTTPException: If authentication fails
        """
        url = f"{settings.SUPABASE_URL}/auth/v1/token?grant_type=password"
        headers = {
            **SUPABASE_HEADERS_ANON,
            'Content-Type': 'application/json',
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    url,
                    json={"email": email, "password": password},
                    headers=headers
                )

            if response.status_code != 200:
                logger.warning(
                    f"Supabase sign-in failed for email={email} status={response.status_code} body={response.text}"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password"
                )

            return response.json()
        except httpx.RequestError as e:
            logger.error(f"Supabase sign-in request failed for email={email}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service unavailable"
            )
    
    @staticmethod
    def sign_out(access_token: str) -> Dict[str, Any]:
        """
        Sign out user by invalidating session.
        
        Args:
            access_token: User's JWT access token
            
        Returns:
            Dict: Sign out response
        """
        url = f"{settings.SUPABASE_URL}/auth/v1/logout"
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    url,
                    headers={
                        **SUPABASE_HEADERS_ANON,
                        "Authorization": f"Bearer {access_token}"
                    }
                )
            return response.json()
        except httpx.RequestError:
            # Even if logout fails on server, we can proceed
            return {"success": True}

    @staticmethod
    def create_user(email: str, password: str) -> Dict[str, Any]:
        """
        Create a new Supabase auth user using the service role key.
        
        Args:
            email: User email
            password: User password

        Returns:
            Dict: Authentication user object
        """
        url = f"{settings.SUPABASE_URL}/auth/v1/admin/users"
        payload = {
            "email": email,
            "password": password,
            "email_confirm": True,
            "app_metadata": {"provider": "email", "providers": ["email"]}
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=SUPABASE_HEADERS_SERVICE
                )

            if response.status_code not in [200, 201]:
                error_detail = response.json().get("msg") if response.headers.get("content-type","").startswith("application/json") else None
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_detail or "Unable to create user"
                )

            return response.json()
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service unavailable"
            )

    @staticmethod
    def delete_user(user_id: str) -> None:
        """
        Delete a Supabase auth user by user ID.
        """
        url = f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}"
        try:
            with httpx.Client(timeout=10.0) as client:
                client.delete(url, headers=SUPABASE_HEADERS_SERVICE)
        except httpx.RequestError as e:
            logger.warning(f"Unable to delete orphan Supabase user {user_id}: {str(e)}")

    @staticmethod
    def fetch_profile_by_id(user_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch user profile from database.
        
        Args:
            user_id: User ID (UUID)
            
        Returns:
            Dict: User profile or None if not found
            
        Raises:
            HTTPException: If database query fails
        """
        url = f"{settings.SUPABASE_URL}/rest/v1/profiles"
        params = {"id": f"eq.{user_id}"}
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    url,
                    headers=SUPABASE_HEADERS_SERVICE,
                    params=params
                )

            if response.status_code != 200:
                body = response.text
                logger.error("Supabase fetch_profile_by_email failed",
                             extra={"status_code": response.status_code, "response": body})
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "message": "Failed to query profiles by email",
                        "status_code": response.status_code,
                        "response": body,
                    }
                )

            results = response.json()
            if not isinstance(results, list) or len(results) == 0:
                return None

            return results[0]
        except httpx.RequestError as req_err:
            logger.exception("Supabase fetch_profile_by_email request error")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "message": "Database request failed",
                    "error": str(req_err),
                    "type": type(req_err).__name__,
                }
            )
    
    @staticmethod
    def fetch_profile_by_email(email: str) -> Optional[Dict[str, Any]]:
        """
        Fetch user profile by email.
        
        Args:
            email: User email
            
        Returns:
            Dict: User profile or None if not found
        """
        url = f"{settings.SUPABASE_URL}/rest/v1/profiles"
        params = {"email": f"eq.{email}"}
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    url,
                    headers=SUPABASE_HEADERS_SERVICE,
                    params=params
                )
            
            if response.status_code != 200:
                return None
            
            results = response.json()
            if not isinstance(results, list) or len(results) == 0:
                return None
            
            return results[0]
        except httpx.RequestError:
            return None
    
    @staticmethod
    def create_profile(
        user_id: str,
        email: str,
        role: str,
        full_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create user profile in database.
        
        Args:
            user_id: User ID (UUID)
            email: User email
            role: User role (CEO or EMPLOYEE)
            full_name: User's full name
            
        Returns:
            Dict: Created profile
            
        Raises:
            HTTPException: If creation fails
        """
        url = f"{settings.SUPABASE_URL}/rest/v1/profiles"
        
        data = {
            "id": user_id,
            "email": email,
            "role": role,
            "full_name": full_name
        }
        
        try:
            # Log the payload we will send to Supabase for debugging schema/constraint issues
            try:
                logger.info(f"Creating profile payload: {data}")
            except Exception:
                logger.debug("Unable to stringify profile payload for logging")

            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    url,
                    json=data,
                    headers={**SUPABASE_HEADERS_SERVICE, "Prefer": "return=representation"}
                )

            if response.status_code not in [200, 201]:
                body = response.text
                logger.error(
                    "Supabase create_profile failed",
                    extra={"status_code": response.status_code, "response": body}
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "message": "Failed to create profile",
                        "status_code": response.status_code,
                        "response": body,
                    }
                )

            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                return result[0]
            return result if isinstance(result, dict) else data
        except httpx.RequestError as req_err:
            logger.exception("Supabase create_profile request error")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "message": "Database request failed",
                    "error": str(req_err),
                    "type": type(req_err).__name__,
                }
            )
    
    @staticmethod
    def update_profile(
        user_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Update user profile.
        
        Args:
            user_id: User ID (UUID)
            **kwargs: Fields to update (full_name, role, etc.)
            
        Returns:
            Dict: Updated profile
            
        Raises:
            HTTPException: If update fails
        """
        url = f"{settings.SUPABASE_URL}/rest/v1/profiles"
        params = {"id": f"eq.{user_id}"}
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.patch(
                    url,
                    json=kwargs,
                    params=params,
                    headers={**SUPABASE_HEADERS_SERVICE, "Prefer": "return=representation"}
                )
            
            if response.status_code not in [200, 204]:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update profile"
                )
            
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                return result[0]
            return kwargs
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database service unavailable"
            )
    
    @staticmethod
    def get_profile_columns() -> List[str]:
        """Return the available columns on the profiles table from the first row metadata."""
        url = f"{settings.SUPABASE_URL}/rest/v1/profiles"
        params = {"select": "*", "limit": "1"}

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    url,
                    headers=SUPABASE_HEADERS_SERVICE,
                    params=params,
                )

            if response.status_code != 200:
                logger.warning("Unable to inspect profiles schema: %s %s", response.status_code, response.text)
                return []

            results = response.json()
            if isinstance(results, list) and results and isinstance(results[0], dict):
                return list(results[0].keys())
            return []
        except httpx.RequestError as exc:
            logger.warning("Profiles schema inspection failed: %s", exc)
            return []

    @staticmethod
    def get_all_profiles(role: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all profiles, optionally filtered by role.
        
        Args:
            role: Optional role to filter by (CEO or EMPLOYEE)
            
        Returns:
            List: List of profiles
        """
        url = f"{settings.SUPABASE_URL}/rest/v1/profiles"
        
        try:
            params = {}
            if role:
                params["role"] = f"eq.{role}"
            
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    url,
                    headers=SUPABASE_HEADERS_SERVICE,
                    params=params
                )
            
            if response.status_code != 200:
                return []
            
            return response.json()
        except httpx.RequestError:
            return []
    
    @staticmethod
    def fetch_profile_by_emp_code(emp_code: str) -> Optional[Dict[str, Any]]:
        """
        Fetch user profile by employee code.
        
        Args:
            emp_code: Employee code from Minerva
            
        Returns:
            Dict: User profile or None if not found
        """
        url = f"{settings.SUPABASE_URL}/rest/v1/profiles"
        params = {"emp_code": f"eq.{emp_code}"}
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    url,
                    headers=SUPABASE_HEADERS_SERVICE,
                    params=params
                )
            
            if response.status_code != 200:
                return None
            
            results = response.json()
            if isinstance(results, list) and len(results) > 0:
                return results[0]
            return None
        except httpx.RequestError:
            return None
    
    @staticmethod
    def upsert_attendance_record(
        employee_id: str,
        attendance_date: str,
        first_punch: str,
        last_punch: str,
        total_hours: float,
        status: str,
        minerva_transaction_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Upsert an attendance record (insert if new, update if exists).
        Treats 409 conflicts (duplicate key) as success since record already synced.
        
        Args:
            employee_id: UUID of the employee
            attendance_date: Date of attendance (YYYY-MM-DD)
            first_punch: First punch timestamp (ISO format)
            last_punch: Last punch timestamp (ISO format)
            total_hours: Total hours worked
            status: Attendance status (PRESENT/ABSENT/HALF_DAY/LEAVE)
            minerva_transaction_id: External Minerva transaction ID
            
        Returns:
            Dict: {"success": True, "data": {...}} on success
                  {"success": True, "data": {...}, "message": "Record already exists"} on 409
                  {"success": False, "error": "message"} on failure
        """
        url = f"{settings.SUPABASE_URL}/rest/v1/attendance_records"
        
        data = {
            "employee_id": employee_id,
            "attendance_date": attendance_date,
            "first_punch": first_punch,
            "last_punch": last_punch,
            "total_hours": total_hours,
            "status": status
        }
        
        if minerva_transaction_id:
            data["minerva_transaction_id"] = minerva_transaction_id
        
        try:
            # Log payload for debugging
            try:
                logger.info(f"Upserting attendance payload: {data}")
            except Exception:
                logger.debug("Unable to stringify attendance payload for logging")

            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    url,
                    json=data,
                    params={"on_conflict": "employee_id,attendance_date"},
                    headers={
                        **SUPABASE_HEADERS_SERVICE,
                        "Prefer": "resolution=merge-duplicates,return=representation"
                    }
                )

            if response.status_code in [200, 201]:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    return {"success": True, "data": result[0]}
                return {"success": True, "data": result if isinstance(result, dict) else data}
            elif response.status_code == 409:
                # Conflict: Record already exists - treat as success (already synced)
                logger.warning(f"Attendance record already exists for employee_id={employee_id} date={attendance_date}")
                return {"success": True, "data": data, "message": "Record already exists"}
            else:
                body = response.text
                try:
                    error_json = response.json()
                    error_msg = error_json.get("message", body)
                except:
                    error_msg = body
                logger.error(f"Upsert attendance failed: {response.status_code} - {error_msg}")
                return {"success": False, "error": error_msg, "status_code": response.status_code}

        except httpx.RequestError as req_err:
            logger.exception("Error upserting attendance record (request error)")
            return {"success": False, "error": str(req_err), "type": "request_error"}
    
    @staticmethod
    def fetch_last_sync_state() -> Optional[Dict[str, Any]]:
        """Fetch the most recent Minerva sync marker for incremental fetches."""
        url = f"{settings.SUPABASE_URL}/rest/v1/minerva_sync_state"
        params = {"select": "*", "id": "eq.global", "limit": "1"}
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=SUPABASE_HEADERS_SERVICE, params=params)
            if response.status_code != 200:
                return None
            results = response.json()
            return results[0] if isinstance(results, list) and results else None
        except httpx.RequestError:
            return None

    @staticmethod
    def upsert_sync_state(records_synced: int, status: str = "OK") -> Dict[str, Any]:
        """Upsert the Minerva sync status for incremental fetch tracking."""
        url = f"{settings.SUPABASE_URL}/rest/v1/minerva_sync_state"
        data = {
            "id": "global",
            "last_sync_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
            "records_synced": records_synced,
            "status": status,
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    url,
                    json=data,
                    params={"on_conflict": "id"},
                    headers={**SUPABASE_HEADERS_SERVICE, "Prefer": "resolution=merge-duplicates,return=representation"},
                )
            if response.status_code in (200, 201):
                result = response.json()
                return result[0] if isinstance(result, list) and result else data
            return {"success": False, "error": response.text}
        except httpx.RequestError as exc:
            return {"success": False, "error": str(exc)}

    @staticmethod
    def upsert_minerva_raw_log(transaction: Dict[str, Any]) -> Dict[str, Any]:
        """Store each Minerva punch event in the raw log table."""
        url = f"{settings.SUPABASE_URL}/rest/v1/minerva_raw_logs"
        payload = {
            "employee_code": str(transaction.get("emp_code") or "").strip(),
            "employee_id": transaction.get("employee_id"),
            "timestamp": transaction.get("punch_time"),
            "raw_payload": transaction,
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers={**SUPABASE_HEADERS_SERVICE, "Prefer": "return=representation"},
                )
            if response.status_code in (200, 201):
                result = response.json()
                return result[0] if isinstance(result, list) and result else payload
            return {"success": False, "error": response.text}
        except httpx.RequestError as exc:
            logger.warning("Failed to store raw Minerva log: %s", exc)
            return {"success": False, "error": str(exc)}

    @staticmethod
    def upsert_daily_attendance_record(
        employee_id: str,
        attendance_date: str,
        first_punch: str,
        last_punch: str,
        working_hours: float,
        attendance_status: str,
    ) -> Dict[str, Any]:
        """Upsert the normalized first/last-punch attendance record for analytics."""
        url = f"{settings.SUPABASE_URL}/rest/v1/attendance_daily"
        data = {
            "employee_id": employee_id,
            "attendance_date": attendance_date,
            "first_punch": first_punch,
            "last_punch": last_punch,
            "working_hours": working_hours,
            "attendance_status": attendance_status,
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    url,
                    json=data,
                    params={"on_conflict": "employee_id,attendance_date"},
                    headers={**SUPABASE_HEADERS_SERVICE, "Prefer": "resolution=merge-duplicates,return=representation"},
                )
            if response.status_code in (200, 201):
                result = response.json()
                return result[0] if isinstance(result, list) and result else {"success": True, "data": data}
            return {"success": False, "error": response.text, "status_code": response.status_code}
        except httpx.RequestError as exc:
            logger.warning("Failed to update daily attendance: %s", exc)
            return {"success": False, "error": str(exc)}

    @staticmethod
    def fetch_attendance_record(
        employee_id: str,
        attendance_date: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch an attendance record by employee and date.
        
        Args:
            employee_id: UUID of the employee
            attendance_date: Date of attendance (YYYY-MM-DD)
            
        Returns:
            Dict: Attendance record or None if not found
        """
        url = f"{settings.SUPABASE_URL}/rest/v1/attendance_records"
        params = {
            "employee_id": f"eq.{employee_id}",
            "attendance_date": f"eq.{attendance_date}"
        }
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    url,
                    headers=SUPABASE_HEADERS_SERVICE,
                    params=params
                )
            
            if response.status_code != 200:
                return None
            
            results = response.json()
            if isinstance(results, list) and len(results) > 0:
                return results[0]
            return None
        except httpx.RequestError:
            return None
    
    @staticmethod
    def revoke_token(user_id: str, jti: str, token_hash: int) -> bool:
        """
        Add token to revocation list.
        
        Args:
            user_id: User ID (UUID)
            jti: JWT ID claim
            token_hash: Hash of the token
            
        Returns:
            bool: True if revocation successful
        """
        url = f"{settings.SUPABASE_URL}/rest/v1/revoked_tokens"
        
        data = {
            "user_id": user_id,
            "jti": jti,
            "token_hash": token_hash,
            "reason": "logout"
        }
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    url,
                    json=data,
                    headers=SUPABASE_HEADERS_SERVICE
                )
            
            return response.status_code in [200, 201]
        except httpx.RequestError:
            return False
    
    @staticmethod
    def check_revoked_token(jti: str, user_id: Optional[str] = None) -> bool:
        """
        Check if token is in revocation list.
        
        Args:
            jti: JWT ID claim
            user_id: Optional user ID for more specific lookup
            
        Returns:
            bool: True if token is revoked
        """
        url = f"{settings.SUPABASE_URL}/rest/v1/revoked_tokens"
        
        try:
            params = {"jti": f"eq.{jti}"}
            if user_id:
                params["user_id"] = f"eq.{user_id}"

            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    url,
                    headers=SUPABASE_HEADERS_SERVICE,
                    params=params
                )

            if response.status_code != 200:
                logger.warning(
                    f"Revocation lookup failed with status {response.status_code}; continuing without revocation enforcement"
                )
                return False

            results = response.json()
            return isinstance(results, list) and len(results) > 0
        except httpx.RequestError as e:
            logger.error(f"Error checking revoked token: {str(e)}")
            return True
    
    @staticmethod
    def cleanup_revoked_tokens(days_old: int = 30) -> int:
        """
        Clean up expired revocations from the database.
        
        Args:
            days_old: Remove revocations older than this many days
            
        Returns:
            int: Number of revocations deleted
        """
        try:
            # Use RPC or direct SQL to delete old revocations
            # For simplicity, we'll use a timestamp comparison
            from datetime import datetime, timedelta
            
            cutoff_date = (datetime.utcnow() - timedelta(days=days_old)).isoformat()
            
            url = f"{settings.SUPABASE_URL}/rest/v1/revoked_tokens"
            params = {"revoked_at": f"lt.{cutoff_date}"}
            
            with httpx.Client(timeout=10.0) as client:
                response = client.delete(
                    url,
                    headers=SUPABASE_HEADERS_SERVICE,
                    params=params
                )
            
            # The response might include the count of deleted rows
            return 0  # Simplified for now
        except httpx.RequestError:
            return 0


# Backward compatibility functions
def sign_in_with_password(email: str, password: str) -> Dict[str, Any]:
    """Sign in user (backward compatible wrapper)."""
    return SupabaseClient.sign_in_with_password(email, password)


def sign_out(access_token: str) -> Dict[str, Any]:
    """Sign out user (backward compatible wrapper)."""
    return SupabaseClient.sign_out(access_token)


def fetch_profile_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch profile by ID (backward compatible wrapper)."""
    return SupabaseClient.fetch_profile_by_id(user_id)

