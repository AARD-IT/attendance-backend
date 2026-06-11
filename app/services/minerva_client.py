"""Minerva Attendance API client using token authentication."""

import logging
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

    def _fetch_paginated(self, url: str, label: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all pages of a paginated Minerva endpoint, optionally filtered by date range."""
        all_items: List[Dict[str, Any]] = []
        current_url = url
        page_number = 1
        params = {key: value for key, value in {"start_date": start_date, "end_date": end_date}.items() if value}

        running_total = 0

        while current_url:
            try:
                response = requests.get(current_url, headers=self.headers, timeout=180, params=params if page_number == 1 else None)
                response.raise_for_status()
                payload = response.json()
            except RequestException as exc:
                logger.error("Minerva %s fetch failed on page %s: %s", label, page_number, exc)
                raise

            if isinstance(payload, dict):
                records = payload.get("data") or []
                current_url = payload.get("next")
            else:
                records = payload
                current_url = None

            if not isinstance(records, list):
                records = []

            running_total += len(records)
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
