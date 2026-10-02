"""Management command: group per-season FEB teams into clubs."""

from django.core.management.base import BaseCommand

from ingestion.clubs import link_clubs


class Command(BaseCommand):
    """Recompute ``Team.club`` links from roster overlap and team names."""

    help = "Group per-season teams of the same club (FEB team ids change yearly)."

    def handle(self, *args, **options) -> None:
        """Run the club-linking pass and print a summary.

        Parameters
        ----------
        *args, **options
            Unused; the command takes no arguments.
        """
        result = link_clubs()
        self.stdout.write(
            self.style.SUCCESS(
                f"{result['clubs']} clubs linking {result['teams_linked']} teams"
            )
        )
