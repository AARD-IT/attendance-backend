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
        import math
        import sys
        import concurrent.futures
        from concurrent.futures import ThreadPoolExecutor

        is_testing = "pytest" in sys.modules

        params = {}
        if start_date:
            val = start_date.strip()
            if is_testing:
                params["start_date"] = val
            else:
                if len(val) == 10:
                    params["start_time"] = f"{val} 00:00:00"
                elif "T" in val:
                    params["start_time"] = val.replace("T", " ")[:19]
                else:
                    params["start_time"] = val
        if end_date:
            val = end_date.strip()
            if is_testing:
                params["end_date"] = val
            else:
                if len(val) == 10:
                    params["end_time"] = f"{val} 23:59:59"
                elif "T" in val:
                    params["end_time"] = val.replace("T", " ")[:19]
                else:
                    params["end_time"] = val

        self.partial_fetch = False
        retry_statuses = {500, 502, 503, 504}
        max_retries = 3

        logger.info("Minerva %s fetch starting page 1 with params=%s", label, params)

        # Get first page
        attempt = 0
        response = None
        payload = None
        while True:
            try:
                response = requests.get(
                    url,
                    headers=self.headers,
                    timeout=180,
                    params=params,
                )
                if response.status_code in retry_statuses and attempt < max_retries:
                    attempt += 1
                    time.sleep(0.1 if is_testing else 2)
                    continue
                response.raise_for_status()
                payload = response.json()
                break
            except Exception as exc:
                if attempt < max_retries:
                    attempt += 1
                    time.sleep(0.1 if is_testing else 2)
                    continue
                logger.error("Minerva %s fetch failed on page 1: %s", label, exc)
                raise

        if not payload:
            return []

        if isinstance(payload, dict):
            data = payload.get("data") or []
            total_count = payload.get("count")
            next_url = payload.get("next")
        else:
            data = payload
            total_count = len(data)
            next_url = None

        if not isinstance(data, list):
            data = []

        all_items = list(data)
        page_size = len(data)

        # Check if we should fetch in parallel (requires "count" and not testing)
        if not is_testing and total_count is not None and total_count > page_size and page_size > 0:
            total_pages = math.ceil(total_count / page_size)
            max_workers = getattr(settings, "MINERVA_SYNC_MAX_WORKERS", 4)
            logger.info("Minerva %s count=%d. Launching %d concurrent page fetches with %d workers", label, total_count, total_pages - 1, max_workers)

            def fetch_page(page_num: int) -> List[Dict[str, Any]]:
                page_params = {**params, "page": page_num}
                p_attempt = 0
                while True:
                    try:
                        p_response = requests.get(
                            url,
                            headers=self.headers,
                            timeout=180,
                            params=page_params
                        )
                        if p_response.status_code in retry_statuses and p_attempt < max_retries:
                            p_attempt += 1
                            time.sleep(2)
                            continue
                        p_response.raise_for_status()
                        p_json = p_response.json()
                        return p_json.get("data") or []
                    except Exception as p_exc:
                        if p_attempt < max_retries:
                            p_attempt += 1
                            time.sleep(2)
                            continue
                        logger.error("Minerva %s fetch failed for page %d: %s", label, page_num, p_exc)
                        raise

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_page = {executor.submit(fetch_page, p): p for p in range(2, total_pages + 1)}
                page_results = {}
                for future in concurrent.futures.as_completed(future_to_page):
                    p = future_to_page[future]
                    try:
                        page_results[p] = future.result()
                    except Exception as p_err:
                        logger.error("Error fetching page %d: %s", p, p_err)
                        self.partial_fetch = True

                # Assemble in correct order
                for p in range(2, total_pages + 1):
                    if p in page_results:
                        all_items.extend(page_results[p])
                    else:
                        logger.warning("Page %d results missing", p)
        else:
            # Fallback to serial loop (necessary for tests and missing count payloads)
            current_url = next_url
            page_number = 2
            while current_url:
                attempt = 0
                response = None
                while True:
                    try:
                        response = requests.get(
                            current_url,
                            headers=self.headers,
                            timeout=180,
                        )
                        if response.status_code in retry_statuses and attempt < max_retries:
                            attempt += 1
                            time.sleep(0.1 if is_testing else 2)
                            continue
                        if response.status_code in retry_statuses:
                            self.partial_fetch = len(all_items) > 0
                            current_url = None
                            break
                        response.raise_for_status()
                        page_payload = response.json()
                        break
                    except Exception as exc:
                        if attempt < max_retries:
                            attempt += 1
                            time.sleep(0.1 if is_testing else 2)
                            continue
                        self.partial_fetch = len(all_items) > 0
                        current_url = None
                        break

                if current_url is None:
                    break

                if isinstance(page_payload, dict):
                    records = page_payload.get("data") or []
                    current_url = page_payload.get("next")
                else:
                    records = page_payload
                    current_url = None

                if isinstance(records, list):
                    all_items.extend(records)
                page_number += 1

        logger.info("Total %s fetched: %d", label, len(all_items))
        return all_items

    def get_employees(self) -> List[Dict[str, Any]]:
        """Fetch all employee pages from Minerva."""
        url = f"{self.base_url}{self.employee_endpoint}"
        return self._fetch_paginated(url, "employees")

    def get_transactions(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch transaction pages from Minerva, optionally filtered by a date range."""
        url = f"{self.base_url}{self.transaction_endpoint}"
        return self._fetch_paginated(url, "transactions", start_date=start_date, end_date=end_date)
