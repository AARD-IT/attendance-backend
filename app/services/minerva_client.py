"""Minerva Attendance API client using token authentication."""

import logging
import time
from typing import Any, Dict, List, Optional

import requests
from requests.exceptions import RequestException

from app.core.config import settings

logger = logging.getLogger(__name__)


class MinervaClient:
    """Client for Minerva attendance API endpoints."""

    def __init__(self) -> None:
        self.base_url = settings.MINERVA_BASE_URL.rstrip('/')
        self.headers = {
            "Authorization": f"Token {settings.MINERVA_API_TOKEN}",
            "Accept": "application/json",
        }
        self.employee_endpoint = settings.MINERVA_EMPLOYEE_ENDPOINT
        self.transaction_endpoint = settings.MINERVA_TRANSACTION_ENDPOINT
        self.partial_fetch = False

    def _fetch_paginated(self, url: str, label: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all pages of a paginated Minerva endpoint, optionally filtered by date range."""
        all_items: List[Dict[str, Any]] = []
        current_url = url
        page_number = 1
        params = {key: value for key, value in {"start_date": start_date, "end_date": end_date}.items() if value}

        running_total = 0
        self.partial_fetch = False
        retry_statuses = {500, 502, 503, 504}
        max_retries = 3

        while current_url:
            attempt = 0
            response = None

            while True:
                try:
                    response = requests.get(
                        current_url,
                        headers=self.headers,
                        timeout=180,
                        params=params if page_number == 1 else None,
                    )

                    if response.status_code in retry_statuses:
                        if attempt < max_retries:
                            attempt += 1
                            logger.warning(
                                "Minerva %s fetch returned status %s on page %s, retrying %s/%s",
                                label,
                                response.status_code,
                                page_number,
                                attempt,
                                max_retries,
                            )
                            time.sleep(2)
                            continue

                        logger.warning("Skipping failed page %s", page_number)
                        self.partial_fetch = len(all_items) > 0
                        current_url = None
                        break

                    response.raise_for_status()
                    payload = response.json()
                    break

                except RequestException as exc:
                    status_code = getattr(response, "status_code", None)
                    if status_code in retry_statuses and attempt < max_retries:
                        attempt += 1
                        logger.warning(
                            "Minerva %s fetch returned status %s on page %s, retrying %s/%s",
                            label,
                            status_code,
                            page_number,
                            attempt,
                            max_retries,
                        )
                        time.sleep(2)
                        continue

                    if status_code in retry_statuses:
                        logger.warning("Skipping failed page %s", page_number)
                        self.partial_fetch = len(all_items) > 0
                        current_url = None
                        break

                    logger.error("Minerva %s fetch failed on page %s: %s", label, page_number, exc)
                    raise

            if current_url is None and response is None and not all_items:
                return []

            if current_url is None and all_items:
                break

            if isinstance(payload, dict):
                records = payload.get("data") or []
                current_url = payload.get("next")
            else:
                records = payload
                current_url = None

            if not isinstance(records, list):
                records = []

            running_total += len(records)
            logger.info("Transactions page=%s records=%s total=%s", page_number, len(records), running_total)
            logger.info(
                "Minerva pagination audit label=%s page=%s records_on_page=%d running_total=%d next=%s",
                label,
                page_number,
                len(records),
                running_total,
                current_url,
            )
            all_items.extend(records)
            page_number += 1

        logger.info("Total %s: %d", label, len(all_items))
        return all_items

    def get_employees(self) -> List[Dict[str, Any]]:
        """Fetch all employee pages from Minerva."""
        url = f"{self.base_url}{self.employee_endpoint}"
        return self._fetch_paginated(url, "employees")

    def get_transactions(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch transaction pages from Minerva, optionally filtered by a date range."""
        url = f"{self.base_url}{self.transaction_endpoint}"
        return self._fetch_paginated(url, "transactions", start_date=start_date, end_date=end_date)
