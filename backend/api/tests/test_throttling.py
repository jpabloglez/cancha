"""Tests for the public API rate limit."""

import pytest
from rest_framework.test import APIClient

from api.throttling import ExternalClientThrottle

URL = "/api/v1/players/?limit=1"  # uncached list endpoint (reaches the view)


@pytest.fixture(autouse=True)
def _tight_limit(monkeypatch) -> None:
    """Use a 3 requests/minute limit so the tests stay small."""
    monkeypatch.setattr(ExternalClientThrottle, "THROTTLE_RATES", {"anon": "3/min"})


def _get(client: APIClient, ip: str | None):
    """Request the API as ``ip`` (via the proxy header) or internally if None."""
    if ip is None:
        return client.get(URL)
    return client.get(URL, HTTP_X_FORWARDED_FOR=ip)


@pytest.mark.django_db
def test_proxied_client_is_limited_per_ip() -> None:
    """The fourth request from one proxied IP gets 429; another IP is unaffected."""
    client = APIClient()
    assert [_get(client, "203.0.113.5").status_code for _ in range(3)] == [200] * 3
    assert _get(client, "203.0.113.5").status_code == 429
    assert _get(client, "203.0.113.9").status_code == 200


@pytest.mark.django_db
def test_internal_requests_are_never_limited() -> None:
    """Server-side rendering calls (no X-Forwarded-For) are exempt."""
    client = APIClient()
    assert all(_get(client, None).status_code == 200 for _ in range(10))
