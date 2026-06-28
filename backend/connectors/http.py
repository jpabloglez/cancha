"""Shared HTTP fetching helper with per-connector rate limiting.

All connectors should fetch through :class:`RateLimitedClient` so the access
frequency to each source stays polite (spec §3.4, §10).
"""

import time

import httpx

DEFAULT_USER_AGENT = (
    "BasketballStatsBot/0.1 (+non-commercial fan project; respects robots.txt)"
)


class RateLimitedClient:
    """Thin wrapper around ``httpx.Client`` enforcing a minimum request gap.

    Parameters
    ----------
    min_interval_seconds : float
        Minimum delay enforced between consecutive requests.
    timeout : float
        Per-request timeout in seconds.
    user_agent : str
        ``User-Agent`` header announcing the bot and its non-commercial intent.

    Attributes
    ----------
    min_interval_seconds : float
        Minimum delay enforced between consecutive requests.
    """

    def __init__(
        self,
        min_interval_seconds: float = 1.0,
        timeout: float = 30.0,
        user_agent: str = DEFAULT_USER_AGENT,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.min_interval_seconds = min_interval_seconds
        self._last_request_at = 0.0
        # Some sources expose a JSON API that needs constant headers on every
        # request (e.g. ACB's public ``X-APIKEY``); merge those in here so
        # callers using ``fetch_or_cache`` don't have to thread headers through.
        headers = {"User-Agent": user_agent}
        if extra_headers:
            headers.update(extra_headers)
        self._client = httpx.Client(
            timeout=timeout,
            headers=headers,
            # Sources migrate legacy .aspx URLs to clean paths via 301s
            # (e.g. FEB Partido.aspx?p=N -> /partido/N); follow them.
            follow_redirects=True,
        )

    def get(self, url: str) -> httpx.Response:
        """Perform a rate-limited GET request.

        Parameters
        ----------
        url : str
            Absolute URL to fetch.

        Returns
        -------
        httpx.Response
            The HTTP response, raised for status on 4xx/5xx.
        """
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - elapsed)
        response = self._client.get(url)
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response

    def close(self) -> None:
        """Close the underlying HTTP client and release the connection pool."""
        self._client.close()
