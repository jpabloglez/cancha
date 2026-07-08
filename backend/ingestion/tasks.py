"""Celery tasks for the asynchronous ingestion pipeline (spec §3.3).

Tasks are scheduled by Celery Beat after each matchday — never during a live
game. Every run is wrapped in an :class:`~ingestion.models.IngestionRun` audit
record, and reingestion is idempotent thanks to ``update_or_create`` keyed by
``(source, external_id)``.
"""

import logging

from celery import shared_task
from django.utils import timezone

from connectors.parsers.acb import ACB_PARSER_VERSION
from connectors.parsers.feb import FEB_PARSER_VERSION
from stats.aggregation import recompute_player_season_aggregates

from .acb_ingest import IngestResult as AcbIngestResult
from .acb_ingest import ingest_acb_season, resolve_current_edition_id
from .catalog import (
    ACB_CONNECTOR_ID,
    FEB_COMPETITIONS,
    resolve_current_feb_season,
)
from .feb_ingest import IngestResult as FebIngestResult
from .feb_ingest import enrich_feb_season, ingest_feb_season
from .models import DataSource, IngestionRun

logger = logging.getLogger(__name__)


@shared_task
def recompute_season_aggregates(season_id: int) -> int:
    """Recompute materialized player aggregates for a season (spec §4.2).

    Parameters
    ----------
    season_id : int
        Primary key of the season to aggregate.

    Returns
    -------
    int
        Number of player aggregates written.
    """
    return recompute_player_season_aggregates(season_id)


def run_ingest_season(connector_id: str, season_external_id: str) -> int:
    """Ingest one season of one source within an audit-record envelope.

    Plain function (no Celery binding) so it can be called from the Celery task,
    from the Beat fan-out task, and from management commands alike.

    Parameters
    ----------
    connector_id : str
        Registered connector id (e.g. "feb-primera").
    season_external_id : str
        Season identifier as used by the external source (FEB: ``t`` year).

    Returns
    -------
    int
        Number of games ingested during the run.

    Raises
    ------
    NotImplementedError
        For connectors whose ingestion flow is not implemented yet.
    """
    data_source = _data_source_for(connector_id)
    run = IngestionRun.objects.create(
        data_source=data_source, parser_version=_parser_version(connector_id)
    )
    try:
        logger.info(
            "Starting ingestion: connector=%s season=%s",
            connector_id,
            season_external_id,
        )
        # FEB seasons are keyed by start year; ACB by the source's editionId.
        # Both flows persist, rebuild rosters and recompute aggregates.
        result: FebIngestResult | AcbIngestResult
        if connector_id in FEB_COMPETITIONS:
            result = ingest_feb_season(connector_id, season_external_id)
        elif connector_id == ACB_CONNECTOR_ID:
            result = ingest_acb_season(season_external_id)
        else:
            raise NotImplementedError(
                f"Ingestion not implemented for connector {connector_id!r}"
            )

        if result.games_failed:
            run.error_log = f"{result.games_failed} game(s) skipped (parse errors)"

        run.records_processed = result.games_ingested
        run.status = IngestionRun.Status.SUCCESS
        run.finished_at = timezone.now()
        run.save(
            update_fields=[
                "records_processed",
                "status",
                "finished_at",
                "error_log",
            ]
        )
        return result.games_ingested
    except Exception as exc:
        run.status = IngestionRun.Status.FAILED
        run.error_log = str(exc)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_log", "finished_at"])
        logger.exception("Ingestion failed for connector=%s", connector_id)
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
)
def ingest_season(self, connector_id: str, season_external_id: str) -> int:
    """Celery task wrapping :func:`run_ingest_season` with retry/backoff.

    Parameters
    ----------
    self : celery.Task
        Bound task instance (enables retry with exponential backoff).
    connector_id : str
        Registered connector id.
    season_external_id : str
        Season identifier as used by the external source.

    Returns
    -------
    int
        Number of games ingested.
    """
    return run_ingest_season(connector_id, season_external_id)


@shared_task
def ingest_current_feb_season() -> dict[str, int]:
    """Ingest the latest season of every FEB competition (Celery Beat entry).

    Scheduled nightly so finished games land within a day (spec §9). Never runs
    during games — it only reads finalized box scores.

    Returns
    -------
    dict of str to int
        Games ingested per connector id.
    """
    return {
        connector_id: run_ingest_season(
            connector_id, resolve_current_feb_season(connector_id)
        )
        for connector_id in FEB_COMPETITIONS
    }


@shared_task
def ingest_current_acb_season() -> int:
    """Ingest the current ACB edition (Celery Beat entry).

    The current ``editionId`` is resolved from the schedule API rather than
    hardcoded, so this keeps working across season rollovers. Scheduled nightly
    so finished games land within a day (spec §9); only finalized box scores are
    read.

    Returns
    -------
    int
        Number of games ingested.
    """
    edition_id = resolve_current_edition_id()
    return run_ingest_season(ACB_CONNECTOR_ID, edition_id)


def run_enrich_season(connector_id: str, season_external_id: str) -> int:
    """Enrich one already-ingested FEB season within an audit-record envelope.

    Plain function (no Celery binding) so it can be called from the Celery task,
    the weekly Beat fan-out and management commands alike.

    Parameters
    ----------
    connector_id : str
        Registered FEB connector id.
    season_external_id : str
        Season identifier as used by the external source (FEB: ``t`` year).

    Returns
    -------
    int
        Number of entities (teams + players) enriched during the run.

    Raises
    ------
    NotImplementedError
        For connectors without a profile-enrichment flow (e.g. ACB for now).
    """
    if connector_id not in FEB_COMPETITIONS:
        raise NotImplementedError(
            f"Enrichment not implemented for connector {connector_id!r}"
        )
    run = IngestionRun.objects.create(
        data_source=_data_source_for(connector_id),
        parser_version=_parser_version(connector_id),
    )
    try:
        result = enrich_feb_season(connector_id, season_external_id)
        processed = result.teams_enriched + result.players_enriched
        if result.failures:
            run.error_log = f"{result.failures} profile(s) skipped (fetch/parse)"
        run.records_processed = processed
        run.status = IngestionRun.Status.SUCCESS
        run.finished_at = timezone.now()
        run.save(
            update_fields=["records_processed", "status", "finished_at", "error_log"]
        )
        return processed
    except Exception as exc:
        run.status = IngestionRun.Status.FAILED
        run.error_log = str(exc)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_log", "finished_at"])
        logger.exception("Enrichment failed for connector=%s", connector_id)
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
)
def enrich_season(self, connector_id: str, season_external_id: str) -> int:
    """Celery task wrapping :func:`run_enrich_season` with retry/backoff.

    Parameters
    ----------
    self : celery.Task
        Bound task instance (enables retry with exponential backoff).
    connector_id : str
        Registered FEB connector id.
    season_external_id : str
        Season identifier as used by the external source.

    Returns
    -------
    int
        Number of entities enriched.
    """
    return run_enrich_season(connector_id, season_external_id)


@shared_task
def enrich_current_feb_profiles() -> dict[str, int]:
    """Enrich the latest season of every FEB competition (weekly Beat entry).

    Profiles change far less often than scores, so this runs on a weekly cadence
    rather than nightly (plan §6.5).

    Returns
    -------
    dict of str to int
        Entities enriched per connector id.
    """
    return {
        connector_id: run_enrich_season(
            connector_id, resolve_current_feb_season(connector_id)
        )
        for connector_id in FEB_COMPETITIONS
    }


def _data_source_for(connector_id: str) -> DataSource:
    """Get or create the DataSource catalogue row for a connector."""
    if connector_id in FEB_COMPETITIONS:
        base_url = FEB_COMPETITIONS[connector_id].base_url
    elif connector_id == ACB_CONNECTOR_ID:
        base_url = "https://api2.acb.com"
    else:
        base_url = "https://baloncestoenvivo.feb.es"
    data_source, _ = DataSource.objects.get_or_create(
        connector_id=connector_id,
        defaults={"name": connector_id, "base_url": base_url},
    )
    return data_source


def _parser_version(connector_id: str) -> str:
    """Return the active parser version recorded on the run."""
    if connector_id in FEB_COMPETITIONS:
        return FEB_PARSER_VERSION
    if connector_id == ACB_CONNECTOR_ID:
        return ACB_PARSER_VERSION
    return ""
