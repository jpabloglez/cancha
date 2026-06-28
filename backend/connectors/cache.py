"""Raw-response cache backed by the database (spec §3.4).

Fetches a URL through a connector's rate-limited client, but first checks for a
recent cached copy in :class:`~ingestion.models.RawDocument`. This lets parsers
be re-run after a fix without re-hitting the source, and keeps an audit trail of
exactly what was parsed.
"""

from datetime import timedelta

from django.utils import timezone

from ingestion.models import RawDocument

from .http import RateLimitedClient

# Default freshness window: within a single ingestion run we reuse a fetched
# page, but across days we re-fetch to pick up corrections/late box scores.
DEFAULT_MAX_AGE = timedelta(hours=12)


def fetch_or_cache(
    url: str,
    *,
    source: str,
    client: RateLimitedClient,
    max_age: timedelta = DEFAULT_MAX_AGE,
    force_refresh: bool = False,
) -> str:
    """Return the body of ``url``, using the cached copy when fresh.

    Parameters
    ----------
    url : str
        Absolute URL to fetch.
    source : str
        Connector id recorded on the cached document.
    client : RateLimitedClient
        Rate-limited HTTP client used on a cache miss.
    max_age : datetime.timedelta
        Maximum age of a cached document before it is considered stale.
    force_refresh : bool
        When True, bypass the cache and always re-fetch.

    Returns
    -------
    str
        The raw response body.
    """
    existing = RawDocument.objects.filter(url=url).first()
    if (
        existing is not None
        and not force_refresh
        and timezone.now() - existing.fetched_at <= max_age
    ):
        return existing.content

    response = client.get(url)
    RawDocument.objects.update_or_create(
        url=url,
        defaults={
            "source": source,
            "content": response.text,
            "status_code": response.status_code,
        },
    )
    return response.text
