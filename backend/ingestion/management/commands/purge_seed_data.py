"""Management command: remove all synthetic seed data from the database.

The ``seed_demo_data`` command populates the DB with deterministic fictional
entities (source="seed") so the frontend works offline without real ingestion.
Once real data is ingested those rows become noise and can contaminate the
leaders/standings pages with fictional players and games.

This command removes every entity whose ``source`` field equals ``"seed"`` and
then drops any seasons that are left with no teams and no games (i.e. seasons
that only ever held seed data and have no real data to show).

It is safe to run after real ingestion has completed. Running it on a DB that
has no seed data is a no-op.

Examples
--------
``python manage.py purge_seed_data``
``python manage.py purge_seed_data --dry-run``
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from games.models import Game
from players.models import CareerEntry, Person, RosterEntry
from teams.models import Season, Team


class Command(BaseCommand):
    """Remove all synthetic seed data (source='seed') from the database."""

    help = (
        "Delete all entities created by seed_demo_data (source='seed') and "
        "prune any seasons that become empty afterwards."
    )

    def add_arguments(self, parser) -> None:
        """Register command-line options.

        Parameters
        ----------
        parser : argparse.ArgumentParser
            Parser provided by Django's command framework.
        """
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be deleted without making any changes.",
        )

    def handle(self, *args, **options) -> None:
        """Execute the purge.

        Parameters
        ----------
        *args
            Unused positional arguments.
        **options
            Parsed options: ``dry_run``.
        """
        dry = options["dry_run"]
        if dry:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be made.\n"))

        # Count before
        teams   = Team.objects.filter(source="seed")
        persons = Person.objects.filter(source="seed")
        games   = Game.objects.filter(source="seed")
        career  = CareerEntry.objects.filter(source="seed")
        roster  = RosterEntry.objects.filter(person__source="seed")

        self.stdout.write(f"Seed entities found:")
        self.stdout.write(f"  Teams:        {teams.count()}")
        self.stdout.write(f"  Persons:      {persons.count()}")
        self.stdout.write(f"  Games:        {games.count()}")
        self.stdout.write(f"  CareerEntry:  {career.count()}")
        self.stdout.write(f"  RosterEntry:  {roster.count()} (cascades from Person)")

        # Seasons that hold seed data but no real data — identified in Python
        # to avoid a complex annotated queryset that can be slow on large DBs.
        seed_season_ids = set(
            Game.objects.filter(source="seed").values_list("season_id", flat=True)
        ) | set(
            Team.objects.filter(source="seed")
            .values_list("team_seasons__season_id", flat=True)
        )
        real_season_ids = set(
            Game.objects.exclude(source="seed").values_list("season_id", flat=True)
        ) | set(
            Team.objects.exclude(source="seed")
            .values_list("team_seasons__season_id", flat=True)
        )
        prune_ids = seed_season_ids - real_season_ids - {None}
        empty_seasons = Season.objects.filter(id__in=prune_ids).select_related("league")

        self.stdout.write(f"  Seasons to prune: {empty_seasons.count()}")
        for s in empty_seasons:
            self.stdout.write(f"    [{s.league.slug}] {s.name} (id={s.id})")

        if dry:
            self.stdout.write(self.style.WARNING("\nDry run complete — nothing deleted."))
            return

        with transaction.atomic():
            # Deleting Teams cascades: TeamSeason → Game (home/away FKs are on
            # TeamSeason) → PlayerGameStats, TeamGameStats, PlayerSeasonAggregate.
            # Deleting Persons cascades: RosterEntry, CareerEntry, PlayerGameStats,
            # PlayerSeasonAggregate (person FK).
            # Order: games first so the TeamSeason→Game cascade doesn't conflict.
            deleted_games, _ = Game.objects.filter(source="seed").delete()
            deleted_persons, _ = Person.objects.filter(source="seed").delete()
            deleted_teams, _  = Team.objects.filter(source="seed").delete()

            # Prune seasons that are now completely empty.
            prunable = Season.objects.filter(id__in=prune_ids).select_related("league")
            pruned_names = [f"[{s.league.slug}] {s.name}" for s in prunable]
            deleted_seasons, _ = Season.objects.filter(id__in=prune_ids).delete()

        self.stdout.write("")
        self.stdout.write(f"Deleted {deleted_games} games")
        self.stdout.write(f"Deleted {deleted_persons} persons (+ cascaded stats)")
        self.stdout.write(f"Deleted {deleted_teams} teams (+ cascaded team-seasons)")
        self.stdout.write(f"Deleted {deleted_seasons} empty seasons:")
        for name in pruned_names:
            self.stdout.write(f"  {name}")
        self.stdout.write(self.style.SUCCESS("Seed data purge complete."))
