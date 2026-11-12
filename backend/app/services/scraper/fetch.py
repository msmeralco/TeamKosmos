"""Polite fetching: identifying User-Agent, robots.txt respected, rate limited, short timeout, one retry."""
from __future__ import annotations

import threading
import time
from typing import Callable
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import httpx

from ...config import get_settings

MIN_INTERVAL_S = 1.0  # at most 1 request/second per site
client_factory: Callable[[], httpx.Client] | None = None  # tests inject a MockTransport client

_last: dict[str, float] = {}
_lock = threading.Lock()


class FetchError(Exception):
    pass


def _client() -> httpx.Client:
    if client_factory:
        return client_factory()
    s = get_settings()
    return httpx.Client(timeout=s.http_timeout_s, headers={"User-Agent": s.user_agent}, follow_redirects=True)


def _wait(host: str) -> None:
    with _lock:
        delay = _last.get(host, 0.0) + MIN_INTERVAL_S - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        _last[host] = time.monotonic()


def allowed_by_robots(base_url: str, path: str) -> bool:
    robots_url = urljoin(base_url, "/robots.txt")
    try:
        with _client() as c:
            resp = c.get(robots_url)
    except httpx.HTTPError:
        return False  # cannot confirm permission -> do not fetch
    if resp.status_code in (404, 410):
        return True
    if resp.status_code != 200:
        return False
    rp = robotparser.RobotFileParser()
    rp.parse(resp.text.splitlines())
    return rp.can_fetch(get_settings().user_agent, urljoin(base_url, path))


def fetch_html(url: str) -> str:
    host = urlparse(url).netloc
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            _wait(host)
            with _client() as c:
                resp = c.get(url)
            resp.raise_for_status()
            if "html" not in resp.headers.get("content-type", "html"):
                raise FetchError("not an HTML page")
            return resp.text
        except (httpx.HTTPError, FetchError) as exc:
            last_exc = exc
    raise FetchError(str(last_exc))
