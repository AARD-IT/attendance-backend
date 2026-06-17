"""Automation job endpoint for Render Scheduled Jobs."""

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Header, HTTPException, status

from app.core.config import settings
from app.services.automation_job_log_service import automation_job_log_service
from app.services.automation_settings_service import automation_settings_service
from app.services.automation_email_service import automation_email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/automation", tags=["automation"])


def _validate_job_token(x_job_token: str | None) -> None:
    expected = str(settings.SCHEDULED_JOB_TOKEN or "").strip()
    if expected and str(x_job_token or "").strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@router.post("/process-due-jobs", status_code=status.HTTP_200_OK)
def process_due_jobs(x_job_token: str | None = Header(default=None, alias="X-Job-Token")) -> Dict[str, Any]:
    _validate_job_token(x_job_token)
    now = datetime.now()
    settings_payload = automation_settings_service.get_settings()
    execution_date = now.date().isoformat()
    summary: Dict[str, Any] = {
        "status": "ok",
        "execution_date": execution_date,
        "jobs": [],
    }

    job_plan = [
        ("monthly_report", automation_email_service.run_monthly_report_job),
        ("late_login_alert", automation_email_service.run_late_login_job),
        ("early_logout_alert", automation_email_service.run_early_logout_job),
    ]

    for job_type, runner in job_plan:
        claimed = automation_job_log_service.claim_job(job_type, execution_date)
        if not claimed:
            summary["jobs"].append({"job_type": job_type, "status": "skipped", "reason": "duplicate"})
            continue

        try:
            result = runner(now=now, settings_payload=settings_payload)
            is_processed = bool(result.get("processed"))
            status_value = "SUCCESS" if is_processed else "SKIPPED"
            automation_job_log_service.finalize_job(job_type, execution_date, status_value, details=result)
            summary["jobs"].append({"job_type": job_type, "status": status_value.lower(), **result})
        except Exception as exc:
            logger.exception("Automation job failed job_type=%s", job_type)
            automation_job_log_service.finalize_job(job_type, execution_date, "FAILED", details={"error": str(exc)})
            summary["jobs"].append({"job_type": job_type, "status": "failed", "error": str(exc)})

    return summary