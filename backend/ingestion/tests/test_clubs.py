"""Tests for club inference across seasons and the club-aware team API."""

from datetime import date

import pytest
from rest_framework.test import APIClient

from ingestion.clubs import (
    link_clubs,
    match_consecutive,
    name_tokens,
    normalize_name,
)
from players.models import Person, RosterEntry
from teams.models import Club, League, Season, Team, TeamSeason


def test_normalize_name_and_tokens() -> None:
    """Names compare ignoring accents, case and punctuation."""
    assert normalize_name("C.B. L´Hospitalet") == normalize_name("CB LHOSPITALET")
    assert name_tokens("ACUNSA GIPUZKOA") & name_tokens("Guuk Gipuzkoa Basket")
    assert not name_tokens("REAL BETIS BALONCESTO") & name_tokens("FLEXICAR FUENLABRADA")


def test_match_consecutive_prefers_exact_name_then_overlap() -> None:
    """Identical names pair first; renamed clubs pair by overlapping rosters."""
    names = {1: "HLA ALICANTE", 2: "ACUNSA GIPUZKOA", 3: "REAL BETIS", 10: "HLA ALICANTE",
             11: "GUUK GIPUZKOA", 12: "FLEXICAR FUENLABRADA"}
    previous = {1: {1}, 2: {1, 2, 3, 4, 5, 6}, 3: {1, 2, 3, 4, 5, 7}}
    following = {10: {9}, 11: {1, 2, 3, 4, 5, 6}, 12: {1, 2, 3, 4, 5, 7}}
    pairs = dict(match_consecutive(previous, following, names))
    assert pairs[1] == 10  # same name
    assert pairs[2] == 11  # renamed, same roster + shared word
    # Betis shares 5 players with the Fuenlabrada roster; strong overlap links.
    assert pairs[3] == 12


def test_match_consecutive_ignores_weak_overlap() -> None:
    """Fewer than 5 shared players without a shared name word is not a link."""
    names = {1: "REAL BETIS", 2: "FLEXICAR FUENLABRADA"}
    assert match_consecutive({1: {1, 2, 3, 4}}, {2: {1, 2, 3, 4}}, names) == []


def _season(league: League, year: int) -> Season:
    """Create a season starting in ``year``."""
    return Season.objects.create(
        league=league, name=f"{year}-{year + 1}", start_date=date(year, 9, 1)
    )


def _team(external_id: str, name: str) -> Team:
    """Create a FEB team row."""
    return Team.objects.create(
        name=name, short_name=name[:3], slug=f"{external_id}-slug",
        source="feb-primera", external_id=external_id,
    )


def _roster(team_season: TeamSeason, persons: list[Person]) -> None:
    """Give a team-season a roster."""
    for person in persons:
        RosterEntry.objects.create(person=person, team_season=team_season)


@pytest.mark.django_db
def test_link_clubs_groups_renamed_club_and_is_idempotent() -> None:
    """A club that changes sponsor/name and id is grouped; others stay apart."""
    league = League.objects.create(name="P", slug="p", level=2, country="ES")
    s1, s2 = _season(league, 2023), _season(league, 2024)
    persons = [
        Person.objects.create(
            first_name="P", last_name=str(i), slug=f"p{i}", source="feb-primera",
            external_id=str(i),
        )
        for i in range(8)
    ]
    old = _team("1", "ACUNSA GIPUZKOA")
    new = _team("2", "GUUK GIPUZKOA BASKET")
    other = _team("3", "OTHER CLUB")
    _roster(TeamSeason.objects.create(team=old, season=s1, league=league), persons[:6])
    _roster(TeamSeason.objects.create(team=new, season=s2, league=league), persons[:6])
    TeamSeason.objects.create(team=other, season=s1, league=league)

    first = link_clubs()
    second = link_clubs()

    assert first == second == {"clubs": 1, "teams_linked": 2}
    old.refresh_from_db(), new.refresh_from_db(), other.refresh_from_db()
    assert old.club_id == new.club_id is not None
    assert other.club_id is None
    assert Club.objects.get().name == "GUUK GIPUZKOA BASKET"


@pytest.mark.django_db
def test_team_api_unifies_club_history_and_dedupes_list() -> None:
    """List shows one team per club; any member slug serves the club's seasons."""
    league = League.objects.create(name="P", slug="p", level=2, country="ES")
    s1, s2 = _season(league, 2023), _season(league, 2024)
    club = Club.objects.create(name="Club", slug="club")
    old, new = _team("1", "OLD NAME"), _team("2", "NEW NAME")
    Team.objects.filter(pk__in=[old.pk, new.pk]).update(club=club)
    TeamSeason.objects.create(team=old, season=s1, league=league)
    TeamSeason.objects.create(team=new, season=s2, league=league)
    client = APIClient()

    listing = client.get("/api/v1/teams/").json()["results"]
    assert [t["name"] for t in listing] == ["NEW NAME"]

    # Staff of the old season is reachable through the newer team's slug.
    old_ts = TeamSeason.objects.get(team=old)
    staff = client.get(f"/api/v1/teams/{new.slug}/staff/?season={old_ts.season_id}")
    assert staff.status_code == 200

    # Roster for the older season resolves via the club even from the new slug.
    roster = client.get(f"/api/v1/teams/{new.slug}/roster/?season={s1.pk}")
    assert roster.status_code == 200


def test_match_consecutive_respects_forbidden_pairs() -> None:
    """A forbidden pair is not linked even with identical names or overlap."""
    names = {1: "A CLUB", 2: "A CLUB", 3: "B CLUB", 4: "B CLUB"}
    forbidden = frozenset({frozenset((1, 2))})
    assert (1, 2) not in match_consecutive({1: {1}}, {2: {1}}, names, forbidden)
    strong = {1: set(range(6))}, {2: set(range(6))}
    assert match_consecutive(*strong, {1: "X ONE", 2: "X ONE"}, forbidden) == []


@pytest.mark.django_db
def test_link_clubs_honours_manual_overrides() -> None:
    """'separate' blocks an overlap-based link; 'merge' forces an unrelated one."""
    from teams.models import ClubLinkOverride

    league = League.objects.create(name="P", slug="p", level=2, country="ES")
    s1, s2 = _season(league, 2023), _season(league, 2024)
    persons = [
        Person.objects.create(
            first_name="P", last_name=str(i), slug=f"q{i}", source="feb-primera",
            external_id=str(i),
        )
        for i in range(6)
    ]
    filial = _team("1", "VALENCIA BC")
    partner = _team("2", "CB GODELLA")
    lone_a, lone_b = _team("3", "ALPHA"), _team("4", "OMEGA")
    _roster(TeamSeason.objects.create(team=filial, season=s1, league=league), persons)
    _roster(TeamSeason.objects.create(team=partner, season=s2, league=league), persons)
    TeamSeason.objects.create(team=lone_a, season=s1, league=league)
    TeamSeason.objects.create(team=lone_b, season=s2, league=league)

    assert link_clubs() == {"clubs": 1, "teams_linked": 2}  # overlap links filial/partner

    ClubLinkOverride.objects.create(
        team_a=filial, team_b=partner, kind=ClubLinkOverride.Kind.SEPARATE
    )
    ClubLinkOverride.objects.create(
        team_a=lone_a, team_b=lone_b, kind=ClubLinkOverride.Kind.MERGE
    )
    assert link_clubs() == {"clubs": 1, "teams_linked": 2}
    filial.refresh_from_db(), partner.refresh_from_db()
    lone_a.refresh_from_db(), lone_b.refresh_from_db()
    assert filial.club_id is None and partner.club_id is None
    assert lone_a.club_id == lone_b.club_id is not None
