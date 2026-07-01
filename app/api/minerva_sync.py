"""
Minerva synchronization API routes.
Provides endpoints for syncing employee and attendance data from Minerva to Supabase.
"""

import logging
from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any

from app.services.minerva_sync import get_minerva_sync_service
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/minerva-sync", tags=["Minerva Sync"])


@router.post("/employees", status_code=status.HTTP_200_OK)
def sync_employees() -> Dict[str, Any]:
    """
    Sync employee data from Minerva to Supabase.
    
    Fetches all employees from Minerva and upserts them into the profiles table.
    Uses emp_code as the unique identifier to prevent duplicates.
    
    Returns:
        Dict containing:
        - success: bool - Whether the sync was successful
        - employees_synced: int - Total number of employees synced
        - inserted: int - Number of new employees inserted
        - updated: int - Number of existing employees updated
        - skipped: int - Number of employees skipped
        - errors: int - Number of errors encountered
        - execution_time_seconds: float - Time taken
    """
    logger.info("Received request to sync employees")
    
    try:
        stats = get_minerva_sync_service().sync_employees()
        
        return {
            "success": stats.get("errors", 0) == 0,
            "employees_synced": stats.get("inserted", 0) + stats.get("updated", 0),
            "inserted": stats.get("inserted", 0),
            "updated": stats.get("updated", 0),
            "skipped": stats.get("skipped", 0),
            "errors": stats.get("errors", 0),
            "execution_time_seconds": stats.get("execution_time_seconds", 0),
            "error_details": stats.get("error_details", [])
        }
    except RequestException as exc:
        logger.error("Minerva employee sync failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Minerva API error: {str(exc)}"
        )
    except Exception as exc:
        logger.error("Employee sync service error", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync service error: {str(exc)}"
        )


@router.post("/attendance", status_code=status.HTTP_200_OK)
def sync_attendance() -> Dict[str, Any]:
    """
    Sync attendance data from Minerva to Supabase.
    
    Fetches all transactions from Minerva and upserts them into the attendance_records table.
    Groups transactions by employee and date, computing first_punch, last_punch, and total_hours.
    Uses minerva_transaction_id to prevent duplicate syncs.
    
    Returns:
        Dict containing:
        - success: bool - Whether the sync was successful
        - attendance_synced: int - Total number of attendance records synced
        - inserted: int - Number of new records inserted
        - updated: int - Number of existing records updated
        - skipped: int - Number of records skipped
        - errors: int - Number of errors encountered
        - execution_time_seconds: float - Time taken
    """
    logger.info("Received request to sync attendance")
    
    try:
        stats = get_minerva_sync_service().sync_attendance()
        
        return {
            "success": stats.get("errors", 0) == 0,
            "attendance_synced": stats.get("inserted", 0) + stats.get("updated", 0),
            "inserted": stats.get("inserted", 0),
            "updated": stats.get("updated", 0),
            "skipped": stats.get("skipped", 0),
            "errors": stats.get("errors", 0),
            "execution_time_seconds": stats.get("execution_time_seconds", 0),
            "error_details": stats.get("error_details", [])
        }
    except RequestException as exc:
        logger.error("Minerva attendance sync failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Minerva API error: {str(exc)}"
        )
    except Exception as exc:
        logger.error("Attendance sync service error", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync service error: {str(exc)}"
        )


from fastapi import BackgroundTasks
from app.db.supabase import SupabaseClient

@router.post("/all", status_code=status.HTTP_200_OK)
def sync_all(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Trigger complete sync in the background (employees first, then attendance).
    """
    logger.info("Received request to run background sync (employees + attendance)")
    
    try:
        latest = SupabaseClient.fetch_sync_status_latest()
        if latest and latest.get("status") == "RUNNING":
            return {
                "success": True,
                "message": "Synchronization is already running in the background.",
                "status": "RUNNING"
            }
            
        background_tasks.add_task(get_minerva_sync_service().sync_all_job)
        return {
            "success": True,
            "message": "Synchronization started in the background...",
            "status": "RUNNING"
        }
    except Exception as exc:
        logger.error("Failed to start background sync", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger sync: {str(exc)}"
        )


@router.get("/status", status_code=status.HTTP_200_OK)
def get_sync_status() -> Dict[str, Any]:
    """
    Get the latest Minerva synchronization status details.
    """
    try:
        latest = SupabaseClient.fetch_sync_status_latest()
        if not latest:
            return {
                "status": "IDLE",
                "last_successful_sync": None,
                "last_attempt": None,
                "records_processed": 0,
                "duration_ms": 0,
                "error_message": None
            }
        return latest
    except Exception as exc:
        logger.error("Failed to fetch sync status", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc)
        )


# Convenience GET endpoints delegates to background poster
@router.get("/employees", status_code=status.HTTP_200_OK)
def sync_employees_get() -> Dict[str, Any]:
    return sync_employees()


@router.get("/attendance", status_code=status.HTTP_200_OK)
def sync_attendance_get() -> Dict[str, Any]:
    return sync_attendance()


@router.get("/debug/{emp_code}/{attendance_date}", status_code=status.HTTP_200_OK)
def debug_attendance(emp_code: str, attendance_date: str) -> Dict[str, Any]:
    """Temporary debug endpoint for a single employee/date attendance group."""
    try:
        return get_minerva_sync_service().debug_attendance(emp_code, attendance_date)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Debug attendance lookup failed", exc_info=exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/all", status_code=status.HTTP_200_OK)
def sync_all_get(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    return sync_all(background_tasks)
