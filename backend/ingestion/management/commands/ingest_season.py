"""Management command: ingest one season of one connector synchronously.

Examples
--------
``python manage.py ingest_season --connector feb-primera --season 2024``
``python manage.py ingest_season --connector acb --season 90``  (ACB editionId)
"""

from django.core.management.base import BaseCommand, CommandError

from ingestion.catalog import ACB_CONNECTOR_ID, FEB_COMPETITIONS
from ingestion.tasks import run_ingest_season

#: Connector ids this command accepts (FEB by start year, ACB by editionId).
_SUPPORTED = (*FEB_COMPETITIONS, ACB_CONNECTOR_ID)


class Command(BaseCommand):
    """Run a single connector/season ingestion in-process."""

    help = "Ingest finished games for one connector and season."

    def add_arguments(self, parser) -> None:
        """Register command-line options.

        Parameters
        ----------
        parser : argparse.ArgumentParser
            Parser provided by Django's command framework.
        """
        parser.add_argument(
            "--connector",
            required=True,
            help=f"Connector id, one of: {', '.join(_SUPPORTED)}",
        )
        parser.add_argument(
            "--season",
            required=True,
            help=(
                "Season identifier as used by the source: FEB start year (e.g. "
                "2024); ACB editionId (e.g. 90 for 2025/2026)."
            ),
        )

    def handle(self, *args, **options) -> None:
        """Run the ingestion and report how many games were ingested.

        Parameters
        ----------
        *args
            Unused positional arguments.
        **options
            Parsed options (``connector``, ``season``).

        Raises
        ------
        CommandError
            If the connector id is unknown.
        """
        connector_id = options["connector"]
        season = options["season"]
        if connector_id not in _SUPPORTED:
            raise CommandError(
                f"Unknown or unsupported connector {connector_id!r}. "
                f"Available: {', '.join(_SUPPORTED)}"
            )
        count = run_ingest_season(connector_id, season)
        self.stdout.write(
            self.style.SUCCESS(
                f"Ingested {count} games for {connector_id} season {season}."
            )
        )
