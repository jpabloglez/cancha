"""Ingestion auditing entities (spec §4.2, §3.3).

``DataSource`` catalogues each external source, and ``IngestionRun`` records
every connector execution for traceability — which connector ran, when, how
many records it processed and whether it failed.
"""

from django.db import models


class DataSource(models.Model):
    """Catalogue entry for an external data source.

    Attributes
    ----------
    name : str
        Human-readable source name (e.g. "ACB.com").
    connector_id : str
        Identifier of the connector that handles this source (e.g. "acb").
    base_url : str
        Base URL of the source.
    type : str
        Source type (official site, aggregator, …).
    """

    class SourceType(models.TextChoices):
        OFFICIAL = "official", "Official"
        AGGREGATOR = "aggregator", "Aggregator"

    name = models.CharField(max_length=100, unique=True)
    connector_id = models.CharField(max_length=50, unique=True)
    base_url = models.URLField()
    type = models.CharField(
        max_length=20, choices=SourceType.choices, default=SourceType.OFFICIAL
    )

    def __str__(self) -> str:
        """Return the source name for admin output."""
        return self.name


class IngestionRun(models.Model):
    """Audit record for a single execution of a connector.

    Attributes
    ----------
    data_source : DataSource
        The source that was ingested.
    started_at : datetime
        When the run started.
    finished_at : datetime or None
        When the run finished, null while running.
    status : str
        Outcome of the run (running, success, failed).
    records_processed : int
        Number of records upserted during the run.
    error_log : str
        Captured error output when the run fails (spec §3.3 traceability).
    """

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    data_source = models.ForeignKey(
        DataSource, on_delete=models.CASCADE, related_name="ingestion_runs"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.RUNNING
    )
    records_processed = models.PositiveIntegerField(default=0)
    error_log = models.TextField(blank=True, default="")
    # Parser version active during the run, recorded so a structural source
    # change can be traced to the parser that produced (or rejected) the data
    # (spec §3.4: versioned parsers, controlled failures).
    parser_version = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        """Return "<source> @ <started_at> [<status>]" for admin output."""
        return f"{self.data_source.name} @ {self.started_at:%Y-%m-%d %H:%M} [{self.status}]"


class RawDocument(models.Model):
    """Cached raw response fetched from a source before parsing (spec §3.4).

    Storing the original HTML/JSON lets parsers be re-run after a bug fix without
    hitting the source again, and provides an audit trail of exactly what was
    parsed. Keyed by URL: the latest fetch per URL is kept (``update_or_create``).

    Attributes
    ----------
    source : str
        Connector id that fetched the document (e.g. "feb-primera").
    url : str
        Absolute URL fetched (the idempotency key).
    content : str
        Raw response body.
    status_code : int
        HTTP status code of the fetch.
    fetched_at : datetime
        When the document was last fetched (used for TTL checks).
    """

    source = models.CharField(max_length=50, db_index=True)
    url = models.URLField(max_length=500, unique=True)
    content = models.TextField()
    status_code = models.PositiveSmallIntegerField(default=200)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fetched_at"]

    def __str__(self) -> str:
        """Return "<source>: <url>" for admin output."""
        return f"{self.source}: {self.url}"
