"""Minerva API routes for attendance and personnel integration."""

import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from requests.exceptions import RequestException

from app.services.minerva_client import MinervaClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/minerva", tags=["Minerva"])


@router.get("/employees")
def employees():
    """Fetch employee data from Minerva."""
    client = MinervaClient()
    try:
        return client.get_employees()
    except RequestException as exc:
        logger.error("Minerva employees fetch failed", exc_info=exc)
        return JSONResponse(
            status_code=502,
            content={"success": False, "message": str(exc)},
        )


@router.get("/transactions")
def transactions():
    """Fetch attendance transactions from Minerva."""
    client = MinervaClient()
    try:
        return client.get_transactions()
    except RequestException as exc:
        logger.error("Minerva transactions fetch failed", exc_info=exc)
        return JSONResponse(
            status_code=502,
            content={"success": False, "message": str(exc)},
        )
