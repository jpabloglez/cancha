"""Tests for the enrichment persistence stage (profiles, media, career).

Covers the fill/refresh-never-clobber contract, idempotency, the media
provenance/takedown rules and career linking
(docs/team-member-enrichment-plan.md §6.3, §7).
"""

from datetime import date

import pytest

from ingestion.persistence import (
    upsert_career_entry,
    upsert_media_asset,
    upsert_person,
    upsert_person_profile,
    upsert_team,
    upsert_team_profile,
)
from ingestion.schemas import (
    ExternalRef,
    NormalizedCareerEntry,
    NormalizedMediaRef,
    NormalizedPerson,
    NormalizedPersonProfile,
    NormalizedTeam,
    NormalizedTeamProfile,
)
from players.models import CareerEntry, Person
from teams.models import MediaAsset, Team


def _ref(external_id: str) -> ExternalRef:
    """Build a seed-source external ref for the given id."""
    return ExternalRef(source="seed", external_id=external_id)


def _media(url: str) -> NormalizedMediaRef:
    """Build a normalized media reference with attribution."""
    return NormalizedMediaRef(
        source="seed",
        source_url=url,
        license="Demo license",
        attribution="Demo attribution",
    )


@pytest.fixture
def team() -> Team:
    """Persist a minimal team (as the box-score path would) for enrichment."""
    return upsert_team(
        NormalizedTeam(
            ref=_ref("t1"),
            name="CB Demo",
            short_name="DEM",
            slug="cb-demo",
            city="Demo City",
        )
    )


@pytest.fixture
def person() -> Person:
    """Persist a minimal person (as the box-score path would) for enrichment."""
    return upsert_person(
        NormalizedPerson(
            ref=_ref("p1"),
            first_name="Carlos",
            last_name="Moreno",
            slug="carlos-moreno-p1",
            nationality="ES",
        )
    )


@pytest.mark.django_db
def test_team_profile_fills_branding_and_creates_logo(team: Team) -> None:
    """A team profile fills branding fields and attaches an attributed logo."""
    upsert_team_profile(
        NormalizedTeamProfile(
            ref=_ref("t1"),
            official_name="Club Baloncesto Demo",
            arena="Pabellón Demo",
            primary_color="#1d4ed8",
            secondary_color="#f59e0b",
            website="https://cb-demo.example",
            logo=_media("https://assets.example/logos/t1.svg"),
        )
    )
    team.refresh_from_db()
    assert team.official_name == "Club Baloncesto Demo"
    assert team.arena == "Pabellón Demo"
    assert team.primary_color == "#1d4ed8"
    assert team.logo is not None
    assert team.logo.kind == MediaAsset.Kind.TEAM_LOGO
    assert team.logo.attribution == "Demo attribution"
    # Reference-only: provenance recorded, no binary stored by the upsert.
    assert not team.logo.file


@pytest.mark.django_db
def test_team_profile_does_not_clobber_known_fields(team: Team) -> None:
    """Fields the profile omits (None) keep their existing values."""
    upsert_team_profile(
        NormalizedTeamProfile(ref=_ref("t1"), official_name="CB Demo Oficial")
    )
    team.refresh_from_db()
    assert team.official_name == "CB Demo Oficial"
    assert team.city == "Demo City"  # not provided by the profile → untouched


@pytest.mark.django_db
def test_person_profile_fills_bio_without_clobbering_identity(
    person: Person,
) -> None:
    """A bio profile fills new fields and never overwrites name/identity."""
    upsert_person_profile(
        NormalizedPersonProfile(
            ref=_ref("p1"),
            birth_date=date(1995, 3, 12),
            birth_city="Sevilla",
            birth_country="ES",
            height_cm=201,
            weight_kg=95,
            primary_position="SF",
            photo=_media("https://assets.example/photos/p1.svg"),
        )
    )
    person.refresh_from_db()
    assert person.first_name == "Carlos"  # identity untouched
    assert person.last_name == "Moreno"
    assert person.nationality == "ES"  # was set; profile omitted → untouched
    assert person.birth_city == "Sevilla"
    assert person.height_cm == 201
    assert person.primary_position == "SF"
    assert person.photo is not None
    assert person.photo.kind == MediaAsset.Kind.PLAYER_PHOTO


@pytest.mark.django_db
def test_person_profile_persists_career_timeline(person: Person) -> None:
    """Career entries are persisted; known clubs link, others stay free text."""
    known_team = upsert_team(
        NormalizedTeam(
            ref=_ref("t9"), name="CB Known", short_name="KNW", slug="cb-known"
        )
    )
    upsert_person_profile(
        NormalizedPersonProfile(
            ref=_ref("p1"),
            career=[
                NormalizedCareerEntry(
                    ref=_ref("p1-c0"),
                    season_label="2024-2025",
                    club_name="CB Known",
                    league_name="Primera FEB",
                    team_ref=_ref("t9"),
                ),
                NormalizedCareerEntry(
                    ref=_ref("p1-c1"),
                    season_label="2022-2023",
                    club_name="CB Foreign (cantera)",
                    league_name="Liga EBA",
                ),
            ],
        )
    )
    entries = {e.external_id: e for e in CareerEntry.objects.filter(person=person)}
    assert len(entries) == 2
    assert entries["p1-c0"].team_id == known_team.id
    assert entries["p1-c1"].team_id is None  # unmapped → free text only


@pytest.mark.django_db
def test_enrichment_is_idempotent(person: Person, team: Team) -> None:
    """Re-running profile upserts creates no duplicate media or career rows."""
    profile = NormalizedPersonProfile(
        ref=_ref("p1"),
        photo=_media("https://assets.example/photos/p1.svg"),
        career=[
            NormalizedCareerEntry(
                ref=_ref("p1-c0"), season_label="2024-2025", club_name="CB Demo"
            )
        ],
    )
    upsert_person_profile(profile)
    upsert_person_profile(profile)
    assert CareerEntry.objects.filter(person=person).count() == 1
    assert MediaAsset.objects.filter(
        source_url="https://assets.example/photos/p1.svg"
    ).count() == 1


@pytest.mark.django_db
def test_media_upsert_preserves_downloaded_file_and_takedown() -> None:
    """Re-recording a ref never clears a stored file or a takedown flag."""
    asset = upsert_media_asset(
        _media("https://assets.example/logos/x.svg"),
        kind=MediaAsset.Kind.TEAM_LOGO,
    )
    # Simulate a later successful download + a rights-holder takedown.
    asset.file.name = "media_assets/x.svg"
    asset.taken_down = True
    asset.save()

    # A subsequent enrichment run re-records the ref with fresh attribution.
    again = upsert_media_asset(
        NormalizedMediaRef(
            source="seed",
            source_url="https://assets.example/logos/x.svg",
            attribution="Updated attribution",
        ),
        kind=MediaAsset.Kind.TEAM_LOGO,
    )
    again.refresh_from_db()
    assert again.pk == asset.pk
    assert again.file.name == "media_assets/x.svg"  # not cleared
    assert again.taken_down is True  # not reset
    assert again.attribution == "Updated attribution"  # refreshed


@pytest.mark.django_db
def test_career_entry_relinks_team_on_update(person: Person) -> None:
    """Upserting a career entry by external id updates its mapped team."""
    team_a = upsert_team(
        NormalizedTeam(ref=_ref("ta"), name="A", short_name="A", slug="a")
    )
    upsert_career_entry(
        NormalizedCareerEntry(
            ref=_ref("p1-c0"),
            season_label="2024-2025",
            club_name="A",
            team_ref=_ref("ta"),
        ),
        person=person,
    )
    assert CareerEntry.objects.get(external_id="p1-c0").team_id == team_a.id
