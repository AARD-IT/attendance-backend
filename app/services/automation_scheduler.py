import logging
import threading
import time
from datetime import datetime
from typing import Optional

from app.services.automation_email_service import automation_email_service
from app.services.ceo_dashboard_settings_service import ceo_dashboard_settings_service
from app.services.minerva_sync import get_minerva_sync_service

logger = logging.getLogger(__name__)


class AutomationScheduler:
    AUTO_REFRESH_INTERVAL_SECONDS = 30 * 60
    SYNC_INTERVAL_SECONDS = 60

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_ceo_refresh_at = 0.0

    def _should_run_ceo_refresh(self, current_time: float | None = None) -> bool:
        current_time = time.monotonic() if current_time is None else current_time
        return (current_time - self._last_ceo_refresh_at) >= self.AUTO_REFRESH_INTERVAL_SECONDS

    def _run_ceo_auto_refresh(self) -> None:
        try:
            row = ceo_dashboard_settings_service.get_settings()
            if not bool(row.get("auto_refresh_enabled")):
                return

            logger.info("Running CEO auto refresh for global settings")
            stats = get_minerva_sync_service().sync_all()
            ceo_dashboard_settings_service.update_last_loaded(
                user_id=None,
                last_loaded_at=datetime.utcnow().isoformat() + 'Z',
                last_loaded_by='auto',
            )
            logger.info("CEO auto refresh completed for global settings stats=%s", stats)
        except Exception as exc:
            logger.warning("CEO auto refresh cycle failed: %s", exc)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                automation_email_service.process_due_jobs()
                if self._should_run_ceo_refresh():
                    self._run_ceo_auto_refresh()
                    self._last_ceo_refresh_at = time.monotonic()
            except Exception as exc:
                logger.warning("automation scheduler tick failed: %s", exc)
            self._stop_event.wait(self.SYNC_INTERVAL_SECONDS)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="automation-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)


automation_scheduler = AutomationScheduler()
