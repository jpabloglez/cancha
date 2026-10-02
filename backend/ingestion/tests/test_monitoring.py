"""Tests for ingestion run bookkeeping and the ingestion health endpoint."""

import logging
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from ingestion import tasks
from ingestion.feb_ingest import EnrichResult
from ingestion.feb_ingest import IngestResult as FebIngestResult
from ingestion.models import DataSource, IngestionRun

HEALTH = "/api/v1/health/ingestion/"


def _patch_ingest(monkeypatch, ingested: int, failed: int) -> None:
    """Make the FEB ingest return fixed counts (no network, no database work)."""
    monkeypatch.setattr(
        tasks, "ingest_feb_season", lambda *_a, **_k: FebIngestResult(ingested, failed)
    )


@pytest.mark.django_db
def test_ingest_where_every_game_fails_is_marked_failed(monkeypatch, caplog) -> None:
    """A structural break (all games failing) fails the run and logs an error."""
    _patch_ingest(monkeypatch, 0, 7)
    with caplog.at_level(logging.ERROR, logger="ingestion.tasks"):
        assert tasks.run_ingest_season("feb-primera", "2025") == 0

    run = IngestionRun.objects.get()
    assert run.status == IngestionRun.Status.FAILED
    assert run.kind == IngestionRun.Kind.INGEST
    assert run.records_failed == 7
    assert "structure change" in run.error_log
    assert any("produced no data" in r.message for r in caplog.records)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("ingested", "failed", "level"),
    [(8, 2, logging.WARNING), (2, 8, logging.ERROR)],
)
def test_partial_ingest_succeeds_and_logs_by_severity(
    monkeypatch, caplog, ingested: int, failed: int, level: int
) -> None:
    """Partial failures keep the run successful; mostly-failed runs log an error."""
    _patch_ingest(monkeypatch, ingested, failed)
    with caplog.at_level(logging.WARNING, logger="ingestion.tasks"):
        assert tasks.run_ingest_season("feb-primera", "2025") == ingested

    run = IngestionRun.objects.get()
    assert run.status == IngestionRun.Status.SUCCESS
    assert (run.records_processed, run.records_failed) == (ingested, failed)
    partial = [r for r in caplog.records if "partially failed" in r.message]
    assert [r.levelno for r in partial] == [level]


@pytest.mark.django_db
def test_enrichment_runs_are_tagged_and_total_failure_is_flagged(monkeypatch) -> None:
    """Enrichment runs use kind=enrich; nothing enriched but failures -> failed."""
    monkeypatch.setattr(
        tasks,
        "enrich_feb_season",
        lambda *_a, **_k: EnrichResult(
            teams_enriched=0, players_enriched=0, staff_ingested=0,
            media_stored=0, failures=3,
        ),
    )
    assert tasks.run_enrich_season("feb-primera", "2025") == 0
    run = IngestionRun.objects.get()
    assert run.kind == IngestionRun.Kind.ENRICH
    assert run.status == IngestionRun.Status.FAILED
    assert run.records_failed == 3


def _run(source: DataSource, kind: str, status: str, hours_ago: float, **extra) -> IngestionRun:
    """Create a finished run that started/finished ``hours_ago`` hours ago."""
    when = timezone.now() - timedelta(hours=hours_ago)
    run = IngestionRun.objects.create(data_source=source, kind=kind, status=status, **extra)
    IngestionRun.objects.filter(pk=run.pk).update(
        started_at=when,
        finished_at=None if status == IngestionRun.Status.RUNNING else when,
    )
    return run


@pytest.fixture
def source(db) -> DataSource:
    """A FEB data source."""
    return DataSource.objects.create(
        name="feb-primera", connector_id="feb-primera", base_url="https://x.test"
    )


def test_health_is_ok_on_a_fresh_install(db) -> None:
    """No sources or no runs yet is not an alert."""
    response = APIClient().get(HEALTH)
    assert response.status_code == 200
    assert response.json() == {"ok": True, "sources": []}


def test_health_ok_with_recent_success(source) -> None:
    """A recent successful run keeps the endpoint at 200."""
    _run(source, "ingest", "success", hours_ago=5, records_processed=300, records_failed=2)
    response = APIClient().get(HEALTH)
    body = response.json()
    assert response.status_code == 200 and body["ok"] is True
    report = body["sources"][0]["runs"]["ingest"]
    assert report["status"] == "ok"
    assert (report["recordsProcessed"], report["recordsFailed"]) == (300, 2)
    assert report["lastSuccessAgeHours"] == pytest.approx(5, abs=0.1)
    assert "enrich" not in body["sources"][0]["runs"]  # never ran: omitted


def test_health_503_when_the_latest_run_failed(source) -> None:
    """A failed latest run alerts even if an older run succeeded; error text is hidden."""
    _run(source, "ingest", "success", hours_ago=30)
    _run(source, "ingest", "failed", hours_ago=2, error_log="secret traceback")
    response = APIClient().get(HEALTH)
    assert response.status_code == 503
    assert response.json()["sources"][0]["runs"]["ingest"]["status"] == "failed"
    assert "secret" not in response.content.decode()


def test_health_503_when_ingestion_is_stale(source) -> None:
    """No success within the limit (36 h) is reported as stale."""
    _run(source, "ingest", "success", hours_ago=72)
    response = APIClient().get(HEALTH)
    assert response.status_code == 503
    assert response.json()["sources"][0]["runs"]["ingest"]["status"] == "stale"


def test_health_judges_enrichment_on_its_own_weekly_schedule(source) -> None:
    """A 3-day-old enrichment is fine; a failed one alerts despite fresh ingestion."""
    _run(source, "ingest", "success", hours_ago=3)
    _run(source, "enrich", "success", hours_ago=72)
    assert APIClient().get(HEALTH).status_code == 200

    _run(source, "enrich", "failed", hours_ago=1)
    response = APIClient().get(HEALTH)
    assert response.status_code == 503
    assert response.json()["sources"][0]["runs"]["ingest"]["status"] == "ok"
    assert response.json()["sources"][0]["runs"]["enrich"]["status"] == "failed"


def test_health_ignores_runs_still_in_progress(source) -> None:
    """A run that is currently running does not mask the last finished one."""
    _run(source, "ingest", "success", hours_ago=4)
    _run(source, "ingest", "running", hours_ago=0.1)
    assert APIClient().get(HEALTH).status_code == 200
