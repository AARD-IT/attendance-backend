from app.services.automation_scheduler import AutomationScheduler


class TestAutomationScheduler:
    def test_should_run_ceo_refresh_only_after_thirty_minutes(self):
        scheduler = AutomationScheduler()

        scheduler._last_ceo_refresh_at = 0.0
        assert scheduler._should_run_ceo_refresh(current_time=1799.0) is False
        assert scheduler._should_run_ceo_refresh(current_time=1800.0) is True

    def test_live_sync_interval_is_sixty_seconds(self):
        scheduler = AutomationScheduler()

        assert scheduler.SYNC_INTERVAL_SECONDS == 60
