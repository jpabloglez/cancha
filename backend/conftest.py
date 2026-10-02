"""Shared pytest fixtures."""

from collections.abc import Iterator

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _isolated_cache(settings) -> Iterator[None]:
    """Give every test a fresh in-memory cache.

    The API wraps most read endpoints in ``cache_page``; with the real Redis
    cache a response cached by one test (with its own data) would leak into the
    next test or the next run. An in-process cache removes that and the need for
    Redis when running tests.
    """
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "pytest",
        }
    }
    cache.clear()
    yield
    cache.clear()
