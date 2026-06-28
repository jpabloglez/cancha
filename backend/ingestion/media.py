"""Media download stage (Option C storage) — spec §10, plan §6.4.

Downloads a :class:`~teams.models.MediaAsset`'s binary from its recorded
``source_url`` (an official free-distribution host) and stores it on the asset,
with a SHA-256 checksum for dedupe. Gated by ``settings.INGEST_STORE_MEDIA`` so
storage can be paused wholesale, and it never touches an asset under a takedown.
Separate from the *profile* upserts, which only record provenance + attribution.
"""

import hashlib
import logging

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from connectors.http import RateLimitedClient
from teams.models import MediaAsset

logger = logging.getLogger(__name__)

#: Content-type -> file extension for the image kinds we accept.
_IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}

#: Reject anything larger than this (defensive; crests/photos are small).
_MAX_BYTES = 5 * 1024 * 1024


def download_media_asset(
    asset_id: int, *, client: RateLimitedClient | None = None, force: bool = False
) -> bool:
    """Download and store one media asset's binary (idempotent).

    Parameters
    ----------
    asset_id : int
        Primary key of the :class:`~teams.models.MediaAsset` to fetch.
    client : RateLimitedClient or None
        HTTP client to use; a polite default is created (and closed) if omitted.
        Injectable so tests can supply a stub.
    force : bool
        Re-download even if a file is already stored (used when refreshing).

    Returns
    -------
    bool
        True when a new binary was stored, False when skipped (storage disabled,
        taken down, already present, non-image, or too large).
    """
    if not settings.INGEST_STORE_MEDIA:
        logger.info("INGEST_STORE_MEDIA disabled; skipping media %s", asset_id)
        return False

    asset = MediaAsset.objects.get(pk=asset_id)
    if asset.taken_down:
        logger.info("Media %s is taken down; not downloading", asset_id)
        return False
    if asset.file and not force:
        return False  # already stored

    owns_client = client is None
    client = client or RateLimitedClient(min_interval_seconds=2.0)
    try:
        response = client.get(asset.source_url)
        content_type = (
            response.headers.get("content-type", "").split(";")[0].strip().lower()
        )
        if not content_type.startswith("image/"):
            logger.warning(
                "Media %s is not an image (content-type=%r); skipping",
                asset_id,
                content_type,
            )
            return False
        content = response.content
        if len(content) > _MAX_BYTES:
            logger.warning("Media %s too large (%d bytes); skipping", asset_id, len(content))
            return False

        checksum = hashlib.sha256(content).hexdigest()
        if asset.checksum == checksum and asset.file:
            return False  # unchanged

        extension = _IMAGE_EXTENSIONS.get(content_type, ".img")
        asset.checksum = checksum
        asset.fetched_at = timezone.now()
        asset.file.save(
            f"{asset.kind}_{asset.pk}{extension}",
            ContentFile(content),
            save=False,
        )
        asset.save(update_fields=["file", "checksum", "fetched_at"])
        logger.info("Stored media %s (%d bytes, %s)", asset_id, len(content), content_type)
        return True
    finally:
        if owns_client:
            client.close()


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
)
def download_media_asset_task(asset_id: int) -> bool:
    """Celery wrapper around :func:`download_media_asset` with retry/backoff.

    Parameters
    ----------
    asset_id : int
        Primary key of the media asset to fetch.

    Returns
    -------
    bool
        Whether a new binary was stored.
    """
    return download_media_asset(asset_id)
