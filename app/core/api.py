"""Shared API client for SafetyCulture API with retry logic and rate limiting."""

import asyncio
import math
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import aiohttp
import requests
import streamlit as st

BASE_URL = "https://api.safetyculture.io"
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2


def get_token() -> str:
    return st.session_state.get("api_token", "")


def get_headers(token: Optional[str] = None) -> Dict[str, str]:
    t = token or get_token()
    return {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {t}",
    }


def validate_token(token: str) -> Tuple[bool, str]:
    """Validate API token by making a lightweight API call."""
    try:
        resp = requests.get(
            f"{BASE_URL}/feed/users?limit=1",
            headers=get_headers(token),
            timeout=10,
        )
        if resp.status_code == 200:
            return True, "Token is valid."
        if resp.status_code == 401:
            return False, "Invalid token. Please check your API key."
        return False, f"Unexpected response: HTTP {resp.status_code}"
    except requests.exceptions.RequestException as e:
        return False, f"Connection error: {e}"


# ---------------------------------------------------------------------------
# Synchronous helpers
# ---------------------------------------------------------------------------


def sync_request(
    method: str,
    endpoint: str,
    token: Optional[str] = None,
    json: Optional[Dict] = None,
    params: Optional[Dict] = None,
    timeout: int = 30,
) -> requests.Response:
    """Make a synchronous request with retry logic."""
    url = endpoint if endpoint.startswith("http") else f"{BASE_URL}{endpoint}"
    headers = get_headers(token)

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.request(
                method, url, headers=headers, json=json, params=params, timeout=timeout
            )
            if resp.status_code not in RETRY_STATUS_CODES or attempt == MAX_RETRIES - 1:
                return resp
            time.sleep(RETRY_BASE_DELAY * (2**attempt))
        except requests.exceptions.RequestException:
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(RETRY_BASE_DELAY * (2**attempt))
    return resp


def sync_paginate_feed(
    endpoint: str, token: Optional[str] = None, data_key: str = "data"
) -> List[Dict]:
    """Paginate through a feed endpoint (GET with next_page in metadata)."""
    url = endpoint if endpoint.startswith("http") else f"{BASE_URL}{endpoint}"
    headers = get_headers(token)
    all_data = []

    while url:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        all_data.extend(body.get(data_key, []))

        next_page = body.get("metadata", {}).get("next_page")
        if next_page:
            url = next_page if next_page.startswith("http") else f"{BASE_URL}{next_page}"
        else:
            url = None

    return all_data


def sync_paginate_post(
    endpoint: str,
    token: Optional[str] = None,
    data_key: str = "items",
    page_size: int = 100,
    token_key: str = "page_token",
    next_token_key: str = "next_page_token",
) -> List[Dict]:
    """Paginate a POST endpoint using page tokens."""
    url = f"{BASE_URL}{endpoint}"
    headers = get_headers(token)
    all_data = []
    page_token = None

    while True:
        payload = {"page_size": page_size}
        if page_token:
            payload[token_key] = page_token

        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        items = body.get(data_key, [])
        all_data.extend(items)

        page_token = body.get(next_token_key)
        if not page_token:
            break

    return all_data


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


class TokenBucketRateLimiter:
    """Token bucket rate limiter for async requests."""

    def __init__(self, requests_per_minute: int):
        self.rate = requests_per_minute / 60.0
        self.burst_size = requests_per_minute
        self.tokens = float(self.burst_size)
        self.last_refill = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self):
        while True:
            async with self._lock:
                now = time.time()
                elapsed = now - self.last_refill
                self.tokens = min(self.burst_size, self.tokens + elapsed * self.rate)
                self.last_refill = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                wait_time = (1.0 - self.tokens) / self.rate
            await asyncio.sleep(wait_time)


def run_async(coro):
    """Run an async coroutine from synchronous Streamlit code."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def create_async_session(
    token: Optional[str] = None, concurrency: int = 30
) -> Tuple[aiohttp.ClientSession, aiohttp.TCPConnector]:
    """Create an aiohttp session with connection pooling."""
    connector = aiohttp.TCPConnector(
        limit=100,
        limit_per_host=concurrency,
        ttl_dns_cache=300,
        use_dns_cache=True,
    )
    timeout = aiohttp.ClientTimeout(total=120, connect=10)
    headers = get_headers(token)
    session = aiohttp.ClientSession(
        headers=headers, connector=connector, timeout=timeout
    )
    return session, connector


async def async_bulk_operation(
    items: List[Any],
    operation_fn: Callable,
    concurrency: int = 20,
    rate_limit: int = 500,
    progress_callback: Optional[Callable] = None,
) -> List[Dict]:
    """Run an async operation on multiple items with rate limiting and progress."""
    semaphore = asyncio.Semaphore(concurrency)
    rate_limiter = TokenBucketRateLimiter(rate_limit)
    results = []
    completed = 0
    total = len(items)

    async def wrapped(item):
        nonlocal completed
        async with semaphore:
            await rate_limiter.acquire()
            result = await operation_fn(item)
            completed += 1
            if progress_callback:
                progress_callback(completed, total)
            return result

    tasks = [wrapped(item) for item in items]
    results = await asyncio.gather(*tasks)
    return list(results)


async def async_paginate_feed(
    endpoint: str, token: Optional[str] = None, data_key: str = "data"
) -> List[Dict]:
    """Async version of feed pagination."""
    session, _ = create_async_session(token)
    url = endpoint if endpoint.startswith("http") else f"{BASE_URL}{endpoint}"
    all_data = []

    try:
        while url:
            async with session.get(url) as resp:
                resp.raise_for_status()
                body = await resp.json()
                all_data.extend(body.get(data_key, []))

                next_page = body.get("metadata", {}).get("next_page")
                if next_page:
                    url = (
                        next_page
                        if next_page.startswith("http")
                        else f"{BASE_URL}{next_page}"
                    )
                else:
                    url = None
    finally:
        await session.close()

    return all_data


async def async_fetch_page_with_retry(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    json: Optional[Dict] = None,
    params: Optional[Dict] = None,
) -> Dict:
    """Fetch a single page with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            async with session.request(method, url, json=json, params=params) as resp:
                if resp.status not in RETRY_STATUS_CODES or attempt == MAX_RETRIES - 1:
                    resp.raise_for_status()
                    return await resp.json()
                await asyncio.sleep(RETRY_BASE_DELAY * (2**attempt))
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt == MAX_RETRIES - 1:
                raise
            await asyncio.sleep(RETRY_BASE_DELAY * (2**attempt))
    return {}
