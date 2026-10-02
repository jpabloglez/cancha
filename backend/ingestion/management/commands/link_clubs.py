"""Management command: group per-season FEB teams into clubs."""

from django.core.management.base import BaseCommand, CommandError

from ingestion.clubs import link_clubs
from teams.models import ClubLinkOverride, Team


class Command(BaseCommand):
    """Recompute ``Team.club`` links, optionally recording manual overrides."""

    help = (
        "Group per-season teams of the same club (FEB team ids change yearly). "
        "Use --separate/--merge to record a manual correction first."
    )

    def add_arguments(self, parser) -> None:
        """Register the optional override arguments.

        Parameters
        ----------
        parser : argparse.ArgumentParser
            The command's argument parser.
        """
        parser.add_argument(
            "--separate", nargs=2, metavar=("SLUG_A", "SLUG_B"),
            help="Record that two team rows are never the same club.",
        )
        parser.add_argument(
            "--merge", nargs=2, metavar=("SLUG_A", "SLUG_B"),
            help="Record that two team rows are always the same club.",
        )
        parser.add_argument("--note", default="", help="Reason for the override.")

    def handle(self, *args, **options) -> None:
        """Store any requested override, then run the club-linking pass.

        Parameters
        ----------
        *args, **options
            Parsed command-line options.

        Raises
        ------
        CommandError
            If both ``--separate`` and ``--merge`` are given or a slug is unknown.
        """
        if options["separate"] and options["merge"]:
            raise CommandError("Use only one of --separate / --merge at a time.")
        for key, kind in (
            ("separate", ClubLinkOverride.Kind.SEPARATE),
            ("merge", ClubLinkOverride.Kind.MERGE),
        ):
            if not options[key]:
                continue
            slug_a, slug_b = options[key]
            try:
                team_a, team_b = Team.objects.get(slug=slug_a), Team.objects.get(slug=slug_b)
            except Team.DoesNotExist as exc:
                raise CommandError(f"Unknown team slug: {exc}") from exc
            ClubLinkOverride.objects.update_or_create(
                team_a=team_a, team_b=team_b,
                defaults={"kind": kind, "note": options["note"]},
            )
            self.stdout.write(f"Recorded {kind}: {slug_a} / {slug_b}")
        result = link_clubs()
        self.stdout.write(
            self.style.SUCCESS(
                f"{result['clubs']} clubs linking {result['teams_linked']} teams"
            )
        )
