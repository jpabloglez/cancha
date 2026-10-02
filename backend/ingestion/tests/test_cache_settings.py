"""Guard: the API cache must not share a Redis database with Celery."""

from django.conf import settings


def test_cache_uses_separate_redis_database_from_celery() -> None:
    """``cache.clear()`` flushes its whole database, so it must not be the broker's."""
    assert settings.CACHES["default"]["LOCATION"] != settings.CELERY_BROKER_URL
