"""
Dashboard service layer.
Handles dashboard-related business logic.
"""

from typing import Dict, Any, Optional
from app.models.profile import Profile
from app.services.auth_service import auth_service


class DashboardService:
    """Service for handling dashboard operations."""
    
    @staticmethod
    def get_ceo_dashboard_data(user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get CEO dashboard data.
        
        Args:
            user_id: User ID (UUID)
            
        Returns:
            Dict: Dashboard data with stats
        """
        profile = auth_service.get_profile(user_id)
        
        if not profile or profile.role != "CEO":
            return None
        
        return {
            "message": "CEO Dashboard",
            "user": {
                "id": profile.id,
                "email": profile.email,
                "role": profile.role,
                "full_name": profile.full_name
            },
            "role": "CEO",
            "stats": {
                "total_employees": 0,  # Placeholder for Phase 2
                "active_sessions": 0,
                "pending_attendance": 0
            }
        }
    
    @staticmethod
    def get_employee_dashboard_data(user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get Employee dashboard data.
        
        Args:
            user_id: User ID (UUID)
            
        Returns:
            Dict: Dashboard data with employee-specific info
        """
        profile = auth_service.get_profile(user_id)
        
        if not profile or profile.role != "EMPLOYEE":
            return None
        
        return {
            "message": "Employee Dashboard",
            "user": {
                "id": profile.id,
                "email": profile.email,
                "role": profile.role,
                "full_name": profile.full_name
            },
            "role": "EMPLOYEE",
            "status": {
                "checkin_status": "checked_out",  # Placeholder for Phase 2
                "last_checkin": None,
                "today_hours": 0.0
            }
        }
    
    @staticmethod
    def build_ceo_dashboard(user: Profile) -> Dict[str, Any]:
        """Build CEO dashboard response (legacy)."""
        return {
            "message": "CEO Dashboard",
            "user": {
                "id": user.id,
                "email": user.email,
                "role": user.role,
                "full_name": user.full_name
            },
            "role": "CEO",
        }
    
    @staticmethod
    def build_employee_dashboard(user: Profile) -> Dict[str, Any]:
        """Build Employee dashboard response (legacy)."""
        return {
            "message": "Employee Dashboard",
            "user": {
                "id": user.id,
                "email": user.email,
                "role": user.role,
                "full_name": user.full_name
            },
            "role": "EMPLOYEE",
        }


# Create global dashboard service instance
dashboard_service = DashboardService()

