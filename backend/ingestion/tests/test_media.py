"""Tests for the gated media download stage (Option C) — plan §6.4.

Uses a stub HTTP client (no network) and a temporary MEDIA_ROOT so nothing is
written outside the test sandbox.
"""

from dataclasses import dataclass

import pytest

from ingestion.media import download_media_asset
from teams.models import MediaAsset

# A 1x1 PNG is unnecessary; the downloader does not decode the image, only checks
# the content-type header and stores the bytes verbatim.
_FAKE_BYTES = b"\x89PNG\r\n\x1a\n-fake-image-bytes"


@dataclass
class _FakeResponse:
    content: bytes
    headers: dict[str, str]

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    """Minimal stand-in for RateLimitedClient returning a fixed response."""

    def __init__(self, content: bytes, content_type: str) -> None:
        self._content = content
        self._content_type = content_type
        self.calls = 0

    def get(self, url: str) -> _FakeResponse:
        self.calls += 1
        return _FakeResponse(self._content, {"content-type": self._content_type})

    def close(self) -> None:
        return None


def _asset() -> MediaAsset:
    return MediaAsset.objects.create(
        kind=MediaAsset.Kind.TEAM_LOGO,
        source="feb-primera",
        source_url="https://imagenes.feb.es/Imagen.aspx?i=1&ti=1",
        attribution="FEB.es",
    )


@pytest.mark.django_db
def test_download_stores_file_and_checksum(settings, tmp_path) -> None:
    """A successful image download is stored with a checksum and fetched_at."""
    settings.MEDIA_ROOT = str(tmp_path)
    settings.INGEST_STORE_MEDIA = True
    asset = _asset()
    client = _FakeClient(_FAKE_BYTES, "image/png")

    stored = download_media_asset(asset.pk, client=client)

    asset.refresh_from_db()
    assert stored is True
    assert asset.file  # binary stored
    assert asset.file.name.endswith(".png")
    assert len(asset.checksum) == 64
    assert asset.fetched_at is not None


@pytest.mark.django_db
def test_download_skipped_when_storage_disabled(settings, tmp_path) -> None:
    """With INGEST_STORE_MEDIA off, nothing is fetched or stored."""
    settings.MEDIA_ROOT = str(tmp_path)
    settings.INGEST_STORE_MEDIA = False
    asset = _asset()
    client = _FakeClient(_FAKE_BYTES, "image/png")

    stored = download_media_asset(asset.pk, client=client)

    asset.refresh_from_db()
    assert stored is False
    assert client.calls == 0  # never hit the network
    assert not asset.file


@pytest.mark.django_db
def test_download_skips_taken_down_asset(settings, tmp_path) -> None:
    """A taken-down asset is never downloaded (rights request honoured)."""
    settings.MEDIA_ROOT = str(tmp_path)
    settings.INGEST_STORE_MEDIA = True
    asset = _asset()
    asset.taken_down = True
    asset.save(update_fields=["taken_down"])
    client = _FakeClient(_FAKE_BYTES, "image/png")

    stored = download_media_asset(asset.pk, client=client)

    assert stored is False
    assert client.calls == 0


@pytest.mark.django_db
def test_download_rejects_non_image(settings, tmp_path) -> None:
    """A non-image response is rejected and nothing is stored."""
    settings.MEDIA_ROOT = str(tmp_path)
    settings.INGEST_STORE_MEDIA = True
    asset = _asset()
    client = _FakeClient(b"<html>not an image</html>", "text/html")

    stored = download_media_asset(asset.pk, client=client)

    asset.refresh_from_db()
    assert stored is False
    assert not asset.file


@pytest.mark.django_db
def test_take_down_removes_binary_and_blocks_redownload(settings, tmp_path) -> None:
    """A takedown deletes the stored file and prevents any re-download."""
    settings.MEDIA_ROOT = str(tmp_path)
    settings.INGEST_STORE_MEDIA = True
    asset = _asset()
    client = _FakeClient(_FAKE_BYTES, "image/png")
    assert download_media_asset(asset.pk, client=client) is True
    asset.refresh_from_db()
    assert asset.file

    asset.take_down()

    asset.refresh_from_db()
    assert asset.taken_down is True
    assert not asset.file  # binary removed
    assert asset.is_available is False
    # Even forcing a re-download is refused while taken down.
    assert download_media_asset(asset.pk, client=client, force=True) is False


@pytest.mark.django_db
def test_download_idempotent_on_unchanged_bytes(settings, tmp_path) -> None:
    """A second download of identical bytes is a no-op (checksum match)."""
    settings.MEDIA_ROOT = str(tmp_path)
    settings.INGEST_STORE_MEDIA = True
    asset = _asset()
    client = _FakeClient(_FAKE_BYTES, "image/png")

    assert download_media_asset(asset.pk, client=client, force=True) is True
    # force=True re-fetches, but identical bytes ⇒ not re-stored.
    assert download_media_asset(asset.pk, client=client, force=True) is False
