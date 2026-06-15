from app.services.automation_scheduler import AutomationScheduler


class TestAutomationScheduler:
    def test_should_run_ceo_refresh_only_after_sixty_minutes(self):
        scheduler = AutomationScheduler()

        scheduler._last_ceo_refresh_at = 0.0
        assert scheduler._should_run_ceo_refresh(current_time=3599.0) is False
        assert scheduler._should_run_ceo_refresh(current_time=3600.0) is True
