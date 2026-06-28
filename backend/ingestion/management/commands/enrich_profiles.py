"""Management command: enrich an ingested FEB season with profiles + logos.

Fetches each team's and player's profile page for a season and persists bio,
branding, trajectory and (optionally) team crests. The box-score ingestion must
have run first — enrichment only fills descriptive data onto existing entities
(docs/team-member-enrichment-plan.md §6.5).

Examples
--------
``python manage.py enrich_profiles --connector feb-primera --season 2025``
``python manage.py enrich_profiles --connector feb-primera --season 2025 --no-media``
"""

from django.core.management.base import BaseCommand, CommandError

from ingestion.catalog import FEB_COMPETITIONS
from ingestion.feb_ingest import enrich_feb_season


class Command(BaseCommand):
    """Enrich one FEB season's teams and players with profile data."""

    help = "Enrich a FEB season with player/team profiles, trajectory and logos."

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
            choices=sorted(FEB_COMPETITIONS),
            help="FEB connector id (feb-primera / feb-segunda).",
        )
        parser.add_argument(
            "--season",
            required=True,
            help="Season start year as used by the source (the 't' parameter).",
        )
        parser.add_argument(
            "--no-media",
            dest="store_media",
            action="store_false",
            help="Skip downloading team logos (persist references only).",
        )

    def handle(self, *args, **options) -> None:
        """Run the enrichment for the requested connector/season.

        Parameters
        ----------
        *args
            Unused positional arguments.
        **options
            Parsed options (``connector``, ``season``, ``store_media``).

        Raises
        ------
        CommandError
            If the connector id is not a known FEB competition.
        """
        connector_id = options["connector"]
        if connector_id not in FEB_COMPETITIONS:
            raise CommandError(f"Unknown FEB connector {connector_id!r}")

        result = enrich_feb_season(
            connector_id,
            options["season"],
            store_media=options["store_media"],
        )
        self.stdout.write(
            f"{connector_id} {options['season']}: "
            f"{result.teams_enriched} teams, {result.players_enriched} players, "
            f"{result.media_stored} logos stored, {result.failures} failures."
        )
        self.stdout.write(self.style.SUCCESS("Enrichment complete."))
