"""Management command: backfill the last N FEB seasons (spec §11, Fase 3).

Enqueues (or runs) one ingestion per (FEB connector, season) for the most recent
``--seasons`` seasons. Idempotent, so it can be re-run to resume after failures.

Examples
--------
``python manage.py backfill --seasons 5``           # all FEB competitions
``python manage.py backfill --seasons 5 --async``   # enqueue via Celery
"""

from django.core.management.base import BaseCommand

from ingestion.catalog import FEB_COMPETITIONS, backfill_start_years
from ingestion.tasks import ingest_season, run_ingest_season


class Command(BaseCommand):
    """Backfill historical FEB seasons across all FEB competitions."""

    help = "Backfill the last N seasons of every FEB competition."

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
            Parsed options (``seasons``, ``use_async``).
        """
        years = backfill_start_years(options["seasons"])
        use_async = options["use_async"]
        self.stdout.write(
            f"Backfilling seasons {years} for {', '.join(FEB_COMPETITIONS)} "
            f"({'async' if use_async else 'in-process'})."
        )
        for connector_id in FEB_COMPETITIONS:
            for year in years:
                season = str(year)
                if use_async:
                    ingest_season.delay(connector_id, season)
                    self.stdout.write(f"  queued {connector_id} {season}")
                    continue
                # Run in-process; isolate each season so a missing/changed older
                # season (spec §12.2) doesn't abort the rest of the backfill.
                try:
                    count = run_ingest_season(connector_id, season)
                    self.stdout.write(f"  {connector_id} {season}: {count} games")
                except Exception as exc:  # noqa: BLE001 - report and continue
                    self.stderr.write(
                        self.style.WARNING(
                            f"  {connector_id} {season}: FAILED ({exc}) — skipping"
                        )
                    )
        self.stdout.write(self.style.SUCCESS("Backfill dispatch complete."))
