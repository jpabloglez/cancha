"""Management command: scrape and store FEB team logos.

Scrapes the official FEB standings pages (www.feb.es/primerafeb and
www.feb.es/segundafeb) to discover team logo URLs, fuzzy-matches them to
existing ``Team`` rows in the database, and persists each logo as a
``MediaAsset``. Optionally downloads the binary immediately.

The command is idempotent: re-running updates existing assets and skips
already-downloaded files.

Examples
--------
``python manage.py fetch_feb_logos --connector feb-primera``
``python manage.py fetch_feb_logos --connector feb-segunda --no-media``
``python manage.py fetch_feb_logos --all``
"""

from django.core.management.base import BaseCommand

from ingestion.feb_logo_scraper import fetch_feb_logos, _STANDINGS_PAGES


class Command(BaseCommand):
    """Scrape and store FEB team logos from the official standings pages."""

    help = (
        "Scrape FEB standings pages (www.feb.es) to discover team logos and "
        "persist them as MediaAsset records."
    )

    def add_arguments(self, parser) -> None:
        """Register command-line options.

        Parameters
        ----------
        parser : argparse.ArgumentParser
            Parser provided by Django's command framework.
        """
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument(
            "--connector",
            choices=sorted(_STANDINGS_PAGES),
            help="Scrape a single FEB competition (feb-primera / feb-segunda).",
        )
        target.add_argument(
            "--all",
            action="store_true",
            dest="all_connectors",
            help="Scrape both Primera FEB and Segunda FEB in sequence.",
        )
        parser.add_argument(
            "--no-media",
            dest="store_media",
            action="store_false",
            help="Record asset provenance only; skip downloading the binary.",
        )

    def handle(self, *args, **options) -> None:
        """Scrape logos for the requested connector(s).

        Parameters
        ----------
        *args
            Unused positional arguments.
        **options
            Parsed options: ``connector``, ``all_connectors``, ``store_media``.
        """
        connector_ids: list[str] = (
            sorted(_STANDINGS_PAGES)
            if options["all_connectors"]
            else [options["connector"]]
        )

        for connector_id in connector_ids:
            self.stdout.write(f"Fetching logos for {connector_id} …")
            result = fetch_feb_logos(
                connector_id,
                store_media=options["store_media"],
            )
            self.stdout.write(
                f"  logos found:    {result.logos_found}\n"
                f"  teams matched:  {result.teams_matched}\n"
                f"  assets created: {result.assets_created}\n"
                f"  binaries stored:{result.media_stored}"
            )
            if result.unmatched:
                self.stdout.write(
                    self.style.WARNING(
                        f"  unmatched ({len(result.unmatched)}): "
                        + ", ".join(result.unmatched)
                    )
                )
            self.stdout.write(self.style.SUCCESS(f"  {connector_id} done."))
