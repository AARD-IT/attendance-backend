from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_process_due_jobs_endpoint_triggers_services(monkeypatch):
    monkeypatch.setattr(
        "app.services.automation_settings_service.automation_settings_service.get_settings",
        lambda: {
            "monthly_report_enabled": True,
            "monthly_report_day": 17,
            "monthly_report_time": "09:00",
            "late_login_enabled": True,
            "late_login_delay": "same_day",
            "late_login_time": "18:00",
            "early_logout_enabled": True,
            "early_logout_delay": "same_day",
            "early_logout_time": "22:30",
        },
    )
    monkeypatch.setattr(
        "app.services.automation_job_log_service.automation_job_log_service.claim_job",
        lambda job_type, execution_date: {"job_type": job_type, "execution_date": execution_date},
    )
    monkeypatch.setattr(
        "app.services.automation_job_log_service.automation_job_log_service.finalize_job",
        lambda *args, **kwargs: {"ok": True},
    )
    monkeypatch.setattr(
        "app.services.automation_email_service.automation_email_service.run_monthly_report_job",
        lambda now=None, settings_payload=None: {"processed": True, "count": 1, "target_month": "2026-05"},
    )
    monkeypatch.setattr(
        "app.services.automation_email_service.automation_email_service.run_late_login_job",
        lambda now=None, settings_payload=None: {"processed": True, "count": 3, "target_date": "2026-06-17"},
    )
    monkeypatch.setattr(
        "app.services.automation_email_service.automation_email_service.run_early_logout_job",
        lambda now=None, settings_payload=None: {"processed": True, "count": 2, "target_date": "2026-06-17"},
    )

    response = client.post("/api/automation/process-due-jobs")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert len(response.json()["jobs"]) == 3


def test_process_due_jobs_requires_valid_token(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.SCHEDULED_JOB_TOKEN", "attendance_prod_secure_token")

    response = client.post("/api/automation/process-due-jobs")

    assert response.status_code == 401