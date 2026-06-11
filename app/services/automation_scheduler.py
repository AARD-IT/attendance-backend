import logging
import threading
from typing import Optional

from app.services.automation_email_service import automation_email_service

logger = logging.getLogger(__name__)


class AutomationScheduler:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                automation_email_service.process_due_jobs()
            except Exception as exc:
                logger.warning("automation scheduler tick failed: %s", exc)
            self._stop_event.wait(60)

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
