"""Seed deterministic synthetic data through the full ingestion pipeline.

Populates the database with **fictional** leagues, teams, players and finished
games so the API and frontend work end-to-end without scraping (spec §13 step 2,
plan: seed-fixtures strategy). Data is generated from a fixed RNG seed and
written via :mod:`ingestion.persistence`, then aggregated via
:mod:`stats.aggregation` — exactly the path a real connector will follow.

Notes
-----
All names are invented to make clear this is demo data, not real ACB/FEB
statistics. Re-running the command is idempotent (upserts keyed by external id).
"""

import random
from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from ingestion.persistence import (
    upsert_game_with_boxscore,
    upsert_league,
    upsert_person,
    upsert_person_profile,
    upsert_roster_entry,
    upsert_season,
    upsert_team,
    upsert_team_profile,
    upsert_team_season,
)
from ingestion.schemas import (
    ExternalRef,
    NormalizedCareerEntry,
    NormalizedGame,
    NormalizedMediaRef,
    NormalizedPerson,
    NormalizedPersonProfile,
    NormalizedPlayerBoxScore,
    NormalizedRosterEntry,
    NormalizedTeam,
    NormalizedTeamBoxScore,
    NormalizedTeamProfile,
)
from stats.aggregation import recompute_player_season_aggregates

SOURCE = "seed"

# Each league: (name, slug, level) plus the fictional cities of its clubs.
LEAGUES = [
    {
        "name": "Liga ACB",
        "slug": "acb",
        "level": 1,
        "cities": ["Almendro", "Robledo", "Marina", "Sierra", "Aurora", "Catedral"],
    },
    {
        "name": "Primera FEB",
        "slug": "primera-feb",
        "level": 2,
        "cities": ["Puerto", "Lirio", "Castillo", "Ribera", "Bahía", "Pinar"],
    },
    {
        "name": "Segunda FEB",
        "slug": "segunda-feb",
        "level": 3,
        "cities": ["Otero", "Vega", "Encina", "Coral", "Duna", "Faro"],
    },
]

SEASONS = [
    {"name": "2023-2024", "start": datetime(2023, 9, 15), "end": datetime(2024, 5, 30)},
    {"name": "2024-2025", "start": datetime(2024, 9, 15), "end": datetime(2025, 5, 30)},
]

FIRST_NAMES = [
    "Álvaro", "Bruno", "Carlos", "Diego", "Eric", "Fran", "Gonzalo", "Hugo",
    "Iván", "Javier", "Koldo", "Lucas", "Marc", "Nico", "Óscar", "Pau",
]
LAST_NAMES = [
    "Aguirre", "Belda", "Cabrera", "Duarte", "Esteban", "Fuentes", "Gallego",
    "Herrero", "Iglesias", "Jordán", "Lozano", "Moreno", "Navarro", "Ortega",
    "Prieto", "Quintana",
]
POSITIONS = ["PG", "SG", "SF", "PF", "C"]
POSITION_HEIGHT = {"PG": 188, "SG": 195, "SF": 201, "PF": 206, "C": 211}

# Deterministic enrichment fixtures (bio / branding / media). Demo media use
# fictitious ".example" URLs and are never downloaded — the seed exercises the
# reference-only path so the frontend can render fallbacks (no real rights at
# stake). See docs/team-member-enrichment-plan.md §4.3, §7.
COLOR_PALETTE = [
    ("#1d4ed8", "#f59e0b"),
    ("#dc2626", "#1f2937"),
    ("#059669", "#fbbf24"),
    ("#7c3aed", "#e5e7eb"),
    ("#0891b2", "#f43f5e"),
    ("#ca8a04", "#111827"),
]
BIRTH_CITIES = [
    "Madrid", "Barcelona", "Sevilla", "Bilbao", "Valencia", "Zaragoza",
    "Málaga", "Murcia", "Vigo", "Granada", "Oviedo", "León",
    "Burgos", "Lugo", "Cádiz", "Huesca",
]
DEMO_MEDIA_LICENSE = "Demo asset — fictional, no real rights involved"
DEMO_MEDIA_ATTRIBUTION = "Seed data (synthetic placeholder, not a real image)"


class Command(BaseCommand):
    """Management command that seeds synthetic demo data."""

    help = "Seed deterministic synthetic leagues, teams, players and games."

    def add_arguments(self, parser) -> None:
        """Register command-line options.

        Parameters
        ----------
        parser : argparse.ArgumentParser
            Parser provided by Django's command framework.
        """
        parser.add_argument(
            "--seed", type=int, default=42, help="RNG seed for reproducibility."
        )

    def handle(self, *args, **options) -> None:
        """Generate and persist the demo dataset.

        Parameters
        ----------
        *args
            Unused positional arguments.
        **options
            Parsed command options (``seed``).

        Returns
        -------
        None
            Writes to the database and prints a summary.
        """
        rng = random.Random(options["seed"])

        for league_cfg in LEAGUES:
            league = upsert_league(
                name=league_cfg["name"],
                slug=league_cfg["slug"],
                level=league_cfg["level"],
            )
            seasons = [
                upsert_season(
                    league=league,
                    name=s["name"],
                    start_date=s["start"].date(),
                    end_date=s["end"].date(),
                )
                for s in SEASONS
            ]

            teams = self._seed_teams(league_cfg)
            self._seed_team_seasons_and_rosters(league, seasons, teams, rng)

            for season, season_cfg in zip(seasons, SEASONS, strict=False):
                self._seed_games(league_cfg, teams, season, season_cfg, rng)
                count = recompute_player_season_aggregates(season.pk)
                self.stdout.write(
                    f"  {league.name} {season.name}: {count} player aggregates"
                )

        self.stdout.write(self.style.SUCCESS("Seed complete."))

    def _seed_teams(self, league_cfg: dict) -> list[dict]:
        """Upsert the clubs of a league and return their descriptors.

        Parameters
        ----------
        league_cfg : dict
            League configuration including its list of fictional cities.

        Returns
        -------
        list of dict
            Per-team descriptors: ``ext`` (external id), ``model`` (Team).
        """
        teams = []
        for idx, city in enumerate(league_cfg["cities"]):
            ext = f"{league_cfg['slug']}-t{idx}"
            normalized = NormalizedTeam(
                ref=ExternalRef(source=SOURCE, external_id=ext),
                name=f"CB {city}",
                short_name=city[:3].upper(),
                slug=slugify(f"{league_cfg['slug']}-{city}"),
                city=city,
                founded_year=1960 + idx,
            )
            teams.append({"ext": ext, "model": upsert_team(normalized), "city": city})

            # Enrich with deterministic branding + a (reference-only) logo.
            primary, secondary = COLOR_PALETTE[idx % len(COLOR_PALETTE)]
            upsert_team_profile(
                NormalizedTeamProfile(
                    ref=ExternalRef(source=SOURCE, external_id=ext),
                    official_name=f"Club Baloncesto {city}",
                    arena=f"Pabellón Municipal de {city}",
                    primary_color=primary,
                    secondary_color=secondary,
                    website=f"https://cb-{slugify(city)}.example",
                    logo=NormalizedMediaRef(
                        source=SOURCE,
                        source_url=f"https://assets.example/seed/logos/{ext}.svg",
                        license=DEMO_MEDIA_LICENSE,
                        attribution=DEMO_MEDIA_ATTRIBUTION,
                    ),
                )
            )
        return teams

    def _seed_team_seasons_and_rosters(
        self, league, seasons: list, teams: list[dict], rng: random.Random
    ) -> None:
        """Create team-seasons and rosters; players persist across seasons.

        Parameters
        ----------
        league : League
            The league being seeded.
        seasons : list of Season
            Seasons to attach participations to.
        teams : list of dict
            Team descriptors from :meth:`_seed_teams`.
        rng : random.Random
            Deterministic RNG.
        """
        for team in teams:
            # Build a stable 10-player roster reused across both seasons so
            # season-over-season trends exist for the same Person.
            roster = []
            # Deterministic name index from a stable string sum — Python's
            # built-in hash() is salted per-process (PYTHONHASHSEED) and would
            # make slugs differ between runs, breaking idempotency.
            ext_seed = sum(ord(c) for c in team["ext"])
            for p in range(10):
                first = FIRST_NAMES[(ext_seed + p) % len(FIRST_NAMES)]
                last = LAST_NAMES[(p * 3 + len(team["ext"])) % len(LAST_NAMES)]
                position = POSITIONS[p % len(POSITIONS)]
                person_ext = f"{team['ext']}-p{p}"
                person = NormalizedPerson(
                    ref=ExternalRef(source=SOURCE, external_id=person_ext),
                    first_name=first,
                    last_name=last,
                    slug=slugify(f"{first}-{last}-{person_ext}"),
                    nationality="ES",
                )
                upsert_person(person)
                self._seed_person_profile(
                    league, team, person_ext, first, last, position, ext_seed, p
                )
                roster.append(
                    {"ext": person_ext, "number": p + 4, "position": position}
                )
            team["roster"] = roster

            for season in seasons:
                team_season = upsert_team_season(
                    team=team["model"], season=season, league=league
                )
                for member in roster:
                    upsert_roster_entry(
                        NormalizedRosterEntry(
                            person_ref=ExternalRef(
                                source=SOURCE, external_id=member["ext"]
                            ),
                            jersey_number=member["number"],
                            position=member["position"],
                            height_cm=POSITION_HEIGHT[member["position"]],
                            weight_kg=rng.randint(80, 115),
                        ),
                        team_season=team_season,
                    )

    def _seed_person_profile(
        self,
        league,
        team: dict,
        person_ext: str,
        first: str,
        last: str,
        position: str,
        ext_seed: int,
        p: int,
    ) -> None:
        """Enrich a seeded person with deterministic bio, photo and trajectory.

        Parameters
        ----------
        league : League
            League the player's current club competes in (for career labels).
        team : dict
            Current-club descriptor (carries ``ext`` and ``city``).
        person_ext : str
            The player's external id.
        first, last : str
            Given and family names.
        position : str
            Playing position (drives the synthetic height).
        ext_seed : int
            Stable per-team seed (sum of ordinals) for reproducible derivation.
        p : int
            Player index within the roster.

        Notes
        -----
        Everything is derived from ``ext_seed`` and ``p`` (never the salted
        builtin ``hash()``) so re-runs are identical. The career timeline lists
        both seeded seasons at the current club plus one unmapped prior club, to
        exercise the linked and free-text branches of ``CareerEntry``.
        """
        birth_year = 1989 + ((ext_seed + p) % 16)
        birth_month = ((ext_seed + p) % 12) + 1
        birth_day = ((p * 7 + ext_seed) % 27) + 1
        career = [
            NormalizedCareerEntry(
                ref=ExternalRef(
                    source=SOURCE, external_id=f"{person_ext}-c{s_idx}"
                ),
                season_label=s["name"],
                club_name=f"CB {team['city']}",
                league_name=league.name,
                team_ref=ExternalRef(source=SOURCE, external_id=team["ext"]),
            )
            for s_idx, s in enumerate(SEASONS)
        ]
        prior_city = BIRTH_CITIES[(ext_seed + p) % len(BIRTH_CITIES)]
        career.append(
            NormalizedCareerEntry(
                ref=ExternalRef(source=SOURCE, external_id=f"{person_ext}-cprior"),
                season_label="2022-2023",
                club_name=f"CB {prior_city} (cantera)",
                league_name="Liga EBA",
                team_ref=None,  # an external club we don't model — stays free text
            )
        )
        upsert_person_profile(
            NormalizedPersonProfile(
                ref=ExternalRef(source=SOURCE, external_id=person_ext),
                display_name=f"{first} {last}",
                birth_date=date(birth_year, birth_month, birth_day),
                birth_city=BIRTH_CITIES[(ext_seed + p * 2) % len(BIRTH_CITIES)],
                birth_country="ES",
                nationality="ES",
                height_cm=POSITION_HEIGHT[position],
                weight_kg=80 + ((ext_seed + p) % 36),
                primary_position=position,
                dominant_hand="L" if (ext_seed + p) % 4 == 0 else "R",
                photo=NormalizedMediaRef(
                    source=SOURCE,
                    source_url=f"https://assets.example/seed/photos/{person_ext}.svg",
                    license=DEMO_MEDIA_LICENSE,
                    attribution=DEMO_MEDIA_ATTRIBUTION,
                ),
                career=career,
            )
        )

    def _seed_games(
        self,
        league_cfg: dict,
        teams: list[dict],
        season,
        season_cfg: dict,
        rng: random.Random,
    ) -> None:
        """Generate a single round-robin of finished games for a season.

        Parameters
        ----------
        league_cfg : dict
            League configuration.
        teams : list of dict
            Team descriptors including rosters.
        season : Season
            Season the games belong to.
        season_cfg : dict
            Season configuration (start datetime).
        rng : random.Random
            Deterministic RNG.
        """
        start = timezone.make_aware(season_cfg["start"])
        round_no = 0
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                round_no += 1
                home, away = teams[i], teams[j]
                home_box, home_players = self._team_box(home, rng)
                away_box, away_players = self._team_box(away, rng)
                game_ext = f"{league_cfg['slug']}-{season.name}-g{round_no}"
                game = NormalizedGame(
                    ref=ExternalRef(source=SOURCE, external_id=game_ext),
                    home_team_ref=ExternalRef(source=SOURCE, external_id=home["ext"]),
                    away_team_ref=ExternalRef(source=SOURCE, external_id=away["ext"]),
                    date=start + timedelta(days=round_no * 3),
                    final_score_home=home_box.points,
                    final_score_away=away_box.points,
                    round=f"J{round_no}",
                    team_box_scores=[home_box, away_box],
                    player_box_scores=home_players + away_players,
                )
                upsert_game_with_boxscore(game, season=season)

    def _team_box(
        self, team: dict, rng: random.Random
    ) -> tuple[NormalizedTeamBoxScore, list[NormalizedPlayerBoxScore]]:
        """Generate a team's box score and its players' lines for one game.

        Parameters
        ----------
        team : dict
            Team descriptor including its roster.
        rng : random.Random
            Deterministic RNG.

        Returns
        -------
        tuple
            The team total box score and the list of player box scores.
        """
        team_ref = ExternalRef(source=SOURCE, external_id=team["ext"])
        player_lines = [
            self._player_line(team_ref, member, rng) for member in team["roster"]
        ]
        totals = {
            field: sum(getattr(line, field) for line in player_lines)
            for field in (
                "points", "rebounds_off", "rebounds_def", "assists", "steals",
                "blocks", "turnovers", "fouls", "field_goals_made",
                "field_goals_att", "three_point_made", "three_point_att",
                "free_throws_made", "free_throws_att",
            )
        }
        team_box = NormalizedTeamBoxScore(team_ref=team_ref, **totals)
        return team_box, player_lines

    def _player_line(
        self, team_ref: ExternalRef, member: dict, rng: random.Random
    ) -> NormalizedPlayerBoxScore:
        """Generate one internally-consistent player box-score line.

        Parameters
        ----------
        team_ref : ExternalRef
            Identity of the player's team.
        member : dict
            Roster descriptor (carries the player's external id).
        rng : random.Random
            Deterministic RNG.

        Returns
        -------
        NormalizedPlayerBoxScore
            A valid, self-consistent stat line (made <= attempted, etc.).
        """
        # Ranges chosen so team totals land in realistic basketball territory
        # (~80-95 pts, ~45 rebounds, ~22 assists) with plausible shooting splits.
        field_goals_att = rng.randint(2, 13)
        field_goals_made = round(field_goals_att * rng.uniform(0.30, 0.55))
        three_point_att = rng.randint(0, min(field_goals_att, 7))
        three_point_made = min(
            field_goals_made, round(three_point_att * rng.uniform(0.20, 0.45))
        )
        free_throws_att = rng.randint(0, 7)
        free_throws_made = round(free_throws_att * rng.uniform(0.60, 0.90))
        points = 2 * field_goals_made + three_point_made + free_throws_made
        return NormalizedPlayerBoxScore(
            person_ref=ExternalRef(source=SOURCE, external_id=member["ext"]),
            team_ref=team_ref,
            minutes_played=rng.randint(6, 30),
            points=points,
            rebounds_off=rng.randint(0, 3),
            rebounds_def=rng.randint(0, 6),
            assists=rng.randint(0, 6),
            steals=rng.randint(0, 3),
            blocks=rng.randint(0, 2),
            turnovers=rng.randint(0, 4),
            fouls=rng.randint(0, 5),
            field_goals_made=field_goals_made,
            field_goals_att=field_goals_att,
            three_point_made=three_point_made,
            three_point_att=three_point_att,
            free_throws_made=free_throws_made,
            free_throws_att=free_throws_att,
        )
