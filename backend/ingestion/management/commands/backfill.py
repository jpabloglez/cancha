"""Management command: backfill the last N seasons for FEB and/or ACB (spec §11, Fase 3).

Enqueues (or runs) one ingestion per season.  Idempotent — re-running the same
range simply updates existing data without creating duplicates.

Examples
--------
``python manage.py backfill``                          # FEB + ACB, 5 seasons
``python manage.py backfill --seasons 3 --source acb`` # ACB only, 3 seasons
``python manage.py backfill --seasons 5 --async``      # enqueue via Celery
"""

import logging

from django.core.management.base import BaseCommand

from ingestion.acb_ingest import resolve_past_edition_ids
from ingestion.catalog import ACB_CONNECTOR_ID, FEB_COMPETITIONS, backfill_start_years
from ingestion.tasks import ingest_season, run_ingest_season

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Backfill historical seasons for FEB competitions and/or the ACB."""

    help = "Backfill the last N seasons for FEB and/or ACB."

    def add_arguments(self, parser) -> None:
        """Register command-line options.

        Parameters
        ----------
        parser : argparse.ArgumentParser
            Parser provided by Django's command framework.
        """
        parser.add_argument(
            "--seasons",
            type=int,
            default=5,
            help="Number of past seasons to backfill (default 5).",
        )
        parser.add_argument(
            "--source",
            choices=["feb", "acb", "all"],
            default="all",
            help="Which source to backfill (default: all).",
        )
        parser.add_argument(
            "--async",
            dest="use_async",
            action="store_true",
            help="Enqueue tasks on Celery instead of running in-process.",
        )

    def handle(self, *args, **options) -> None:
        """Run or enqueue the backfill across competitions and seasons.

        Parameters
        ----------
        *args
            Unused positional arguments.
        **options
            Parsed options: ``seasons``, ``source``, ``use_async``.
        """
        count = options["seasons"]
        source = options["source"]
        use_async = options["use_async"]

        if source in ("feb", "all"):
            self._backfill_feb(count, use_async)
        if source in ("acb", "all"):
            self._backfill_acb(count, use_async)

        self.stdout.write(self.style.SUCCESS("Backfill dispatch complete."))

    def _backfill_feb(self, count: int, use_async: bool) -> None:
        """Backfill the last *count* FEB seasons for every FEB competition.

        Parameters
        ----------
        count : int
            Number of seasons to backfill.
        use_async : bool
            Whether to enqueue via Celery instead of running in-process.
        """
        years = backfill_start_years(count)
        self.stdout.write(
            f"FEB backfill: seasons {years} for {', '.join(FEB_COMPETITIONS)} "
            f"({'async' if use_async else 'in-process'})."
        )
        for connector_id in FEB_COMPETITIONS:
            for year in years:
                season = str(year)
                if use_async:
                    ingest_season.delay(connector_id, season)
                    self.stdout.write(f"  queued {connector_id} {season}")
                    continue
                try:
                    count_games = run_ingest_season(connector_id, season)
                    self.stdout.write(f"  {connector_id} {season}: {count_games} games")
                except Exception as exc:  # noqa: BLE001 - report and continue
                    self.stderr.write(
                        self.style.WARNING(
                            f"  {connector_id} {season}: FAILED ({exc}) — skipping"
                        )
                    )

    def _backfill_acb(self, count: int, use_async: bool) -> None:
        """Backfill the last *count* ACB seasons by edition id.

        Parameters
        ----------
        count : int
            Number of editions to backfill.
        use_async : bool
            Whether to enqueue via Celery instead of running in-process.

        Notes
        -----
        The edition id list is resolved from the ACB schedule API, which returns
        the full history of editions in its ``availableFilters.seasons`` block.
        The most recent *count* editions are selected by descending start year.
        """
        self.stdout.write(f"ACB backfill: resolving last {count} editions…")
        try:
            edition_ids = resolve_past_edition_ids(count)
        except Exception as exc:  # noqa: BLE001 - network may be unavailable
            self.stderr.write(
                self.style.ERROR(f"ACB: could not resolve edition ids: {exc} — skipping")
            )
            return

        self.stdout.write(
            f"ACB backfill: editions {edition_ids} "
            f"({'async' if use_async else 'in-process'})."
        )
        for edition_id in edition_ids:
            if use_async:
                ingest_season.delay(ACB_CONNECTOR_ID, edition_id)
                self.stdout.write(f"  queued acb edition {edition_id}")
                continue
            try:
                count_games = run_ingest_season(ACB_CONNECTOR_ID, edition_id)
                self.stdout.write(f"  acb edition {edition_id}: {count_games} games")
            except Exception as exc:  # noqa: BLE001 - report and continue
                self.stderr.write(
                    self.style.WARNING(
                        f"  acb edition {edition_id}: FAILED ({exc}) — skipping"
                    )
                )
