"""Guard: the API cache must not share a Redis database with Celery."""

from config import settings as project_settings


def test_cache_uses_separate_redis_database_from_celery() -> None:
    """``cache.clear()`` flushes its whole database, so it must not be the broker's.

    Reads the project settings module directly because the test suite swaps the
    live cache for an in-memory one (see ``conftest.py``).
    """
    cache_url = project_settings.CACHES["default"]["LOCATION"]
    assert cache_url != project_settings.CELERY_BROKER_URL
