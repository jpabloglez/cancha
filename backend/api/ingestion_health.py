"""Health endpoint for the ingestion pipeline, meant for an external monitor."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from ingestion.models import DataSource, IngestionRun


def _kind_report(
    source: DataSource, kind: str, max_age: timedelta, now
) -> dict | None:
    """Summarise the latest runs of one kind for one source.

    Parameters
    ----------
    source : DataSource
        Source to inspect.
    kind : str
        An ``IngestionRun.Kind`` value.
    max_age : datetime.timedelta
        Longest tolerated time since the last successful run.
    now : datetime.datetime
        Current time (injected for clarity).

    Returns
    -------
    dict or None
        Report with ``status`` (``ok``, ``failed``, ``stale``), or ``None`` when
        the source has no finished run of this kind (nothing to judge yet).
    """
    finished = source.ingestion_runs.filter(kind=kind).exclude(
        status=IngestionRun.Status.RUNNING
    )
    last = finished.first()  # ordered newest first
    if last is None:
        return None
    last_success = finished.filter(status=IngestionRun.Status.SUCCESS).first()
    age = (now - last_success.finished_at) if last_success and last_success.finished_at else None

    if last.status == IngestionRun.Status.FAILED:
        state = "failed"
    elif age is None or age > max_age:
        state = "stale"
    else:
        state = "ok"
    return {
        "status": state,
        "lastRunStatus": last.status,
        "lastRunAt": last.started_at.isoformat(),
        "lastSuccessAt": last_success.finished_at.isoformat()
        if last_success and last_success.finished_at
        else None,
        "lastSuccessAgeHours": round(age.total_seconds() / 3600, 1) if age else None,
        "recordsProcessed": last.records_processed,
        "recordsFailed": last.records_failed,
    }


@api_view(["GET"])
def ingestion_health(request: Request) -> Response:
    """Report whether scheduled ingestion is running and succeeding.

    Per source and run kind (games ingestion, profile enrichment) the latest
    finished run must not have failed and the last success must be recent
    (``INGESTION_MAX_AGE_HOURS`` for games, ``ENRICH_MAX_AGE_DAYS`` for
    profiles). Kinds that never ran are omitted so a fresh install is healthy.
    Error text is deliberately not exposed.

    Parameters
    ----------
    request : rest_framework.request.Request
        Incoming request.

    Returns
    -------
    rest_framework.response.Response
        ``{"ok": bool, "sources": [...]}`` with HTTP 200 when healthy and 503
        otherwise, so a plain uptime monitor can alert on the status code.
    """
    now = timezone.now()
    limits = {
        IngestionRun.Kind.INGEST: timedelta(hours=settings.INGESTION_MAX_AGE_HOURS),
        IngestionRun.Kind.ENRICH: timedelta(days=settings.ENRICH_MAX_AGE_DAYS),
    }
    sources = []
    healthy = True
    for source in DataSource.objects.order_by("connector_id"):
        reports = {}
        for kind, max_age in limits.items():
            report = _kind_report(source, kind, max_age, now)
            if report is not None:
                reports[kind.value] = report
                healthy = healthy and report["status"] == "ok"
        sources.append({"source": source.connector_id, "runs": reports})
    return Response(
        {"ok": healthy, "sources": sources},
        status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
