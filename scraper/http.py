"""Polite HTTP: one plain user agent, robots.txt, a fixed delay, no retries on 403/429."""
from __future__ import annotations

import logging
import time
import urllib.robotparser
from urllib.parse import urlsplit

import requests

log = logging.getLogger(__name__)

USER_AGENT = "idf-rent personal rental aggregator (+https://github.com/; contact via repo issues)"


class SourceBlocked(Exception):
    """Raised on HTTP 403/429 (or an unreadable robots.txt). The source stops for this run."""


class PoliteSession:
    def __init__(self, delay: float = 1.5, timeout: float = 30.0):
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._last_request = 0.0
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request = time.monotonic()

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        rp = self._robots.get(host)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            self._wait()
            resp = self.session.get(f"{host}/robots.txt", timeout=self.timeout)
            if resp.status_code in (403, 429):
                raise SourceBlocked(f"{host}/robots.txt returned {resp.status_code}")
            if resp.ok:
                rp.parse(resp.text.splitlines())
            else:
                rp.parse([])  # no robots.txt: everything allowed
            self._robots[host] = rp
        return rp.can_fetch(USER_AGENT, url)

    def get(self, url: str, **kwargs) -> requests.Response:
        if not self._allowed(url):
            raise SourceBlocked(f"robots.txt disallows {url}")
        self._wait()
        resp = self.session.get(url, timeout=self.timeout, allow_redirects=False, **kwargs)
        if resp.status_code in (403, 429):
            raise SourceBlocked(f"{url} returned HTTP {resp.status_code}; stopping, not retrying")
        return resp

    def get_asset(self, url: str) -> requests.Response:
        """Fetch an embedded asset (a photo on a CDN) the way a browser rendering the ad
        would: same user agent, a short delay, no robots.txt lookup on the CDN host."""
        elapsed = time.monotonic() - self._last_request
        if elapsed < 0.3:
            time.sleep(0.3 - elapsed)
        self._last_request = time.monotonic()
        return self.session.get(url, timeout=self.timeout)

    def head(self, url: str) -> requests.Response:
        """Status-only request used by the liveness pass. Falls back to GET when HEAD is refused."""
        if not self._allowed(url):
            raise SourceBlocked(f"robots.txt disallows {url}")
        self._wait()
        resp = self.session.head(url, timeout=self.timeout, allow_redirects=False)
        if resp.status_code in (405, 501):
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=False, stream=True)
            resp.close()
        if resp.status_code in (403, 429):
            raise SourceBlocked(f"{url} returned HTTP {resp.status_code}; stopping, not retrying")
        return resp
