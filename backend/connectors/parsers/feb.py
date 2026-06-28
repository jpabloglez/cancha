"""Parsers for FEB pages (baloncestoenvivo.feb.es) — spec §3.3.

Pure functions turning raw HTML into validated ``ingestion.schemas`` objects.
No I/O, no DB — so they are unit-tested against saved HTML fixtures.

Design notes
------------
Parsing is **header- and link-driven** rather than tied to fragile CSS classes:
player/team identity comes from ``Jugador.aspx?i=<team>&c=<player>`` links, and
stat columns are mapped by their header text (Spanish abbreviations). The box
score header repeats ``TC`` (field goals *and* tapones-contra); the column map
keeps the **first** occurrence, which is the field-goal column we want.

Box-score column meanings (spec §4: discovery 2026-06-21)::

    MIN PT T2 T3 TC TL RO RD RT AS BR BP TF TC MT FC FR VA +/-
                  └ field goals (made/att)         └ tapones-contra (ignored)
    T3 = three-pointers, TL = free throws, RO/RD = off/def rebounds,
    BR = steals, BP = turnovers, TF = blocks, FC = fouls.

These parsers were validated against a representative fixture; confirm against
captured raw HTML before the first production run (see implementation plan §4).
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime

from bs4 import BeautifulSoup
from django.utils import timezone
from django.utils.text import slugify

from ingestion.schemas import (
    ExternalRef,
    NormalizedCareerEntry,
    NormalizedGame,
    NormalizedMediaRef,
    NormalizedPerson,
    NormalizedPersonProfile,
    NormalizedPlayerBoxScore,
    NormalizedTeam,
    NormalizedTeamBoxScore,
    NormalizedTeamProfile,
)

#: Bumped when the parsing logic changes; recorded on each IngestionRun (§3.4).
#: ``p`` suffix marks the addition of the profile (bio/branding/career) parsers.
FEB_PARSER_VERSION = "feb-2026.06p"

# Header text -> our schema field, for the columns we keep.
_PLAYER_COLUMNS = {
    "MIN": "minutes",
    "PT": "points",
    "T3": "three_point",
    "TC": "field_goals",
    "TL": "free_throws",
    "RO": "rebounds_off",
    "RD": "rebounds_def",
    "AS": "assists",
    "BR": "steals",
    "BP": "turnovers",
    "TF": "blocks",
    "FC": "fouls",
}

# Game links appear as the legacy "Partido.aspx?p=N" or the clean "/partido/N".
_GAME_ID_RE = re.compile(r"(?:Partido\.aspx\?p=|/partido/)(\d+)", re.IGNORECASE)
_PLAYER_LINK_RE = re.compile(r"Jugador\.aspx\?i=(\d+)&c=(\d+)", re.IGNORECASE)
_TEAM_LINK_RE = re.compile(r"Equipo\.aspx\?i=(\d+)", re.IGNORECASE)
_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?")

# Team crest, served by FEB's own image host (free distribution, verified to
# return image/jpeg). ``ti=1`` is the primary crest. See plan §5.3.
_LOGO_URL = "https://imagenes.feb.es/Imagen.aspx?i={i}&ti=1"
_LOGO_RE = re.compile(r"imagenes\.feb\.es/Imagen\.aspx\?i=\d+&ti=1", re.IGNORECASE)
_FEB_IMAGE_LICENSE = "©FEB / club — imagenes.feb.es (free distribution)"
_FEB_IMAGE_ATTRIBUTION = "FEB.es"

# Spanish "Puesto" (position) -> our 2-letter code (accent-stripped, lower key).
_POSITION_MAP = {
    "base": "PG",
    "escolta": "SG",
    "alero": "SF",
    "ala-pivot": "PF",
    "ala pivot": "PF",
    "pivot": "C",
}

# Spanish country names -> ISO 3166-1 alpha-2 (accent-stripped, upper key). Only
# the nationalities common in Spanish leagues; an unknown name maps to None
# rather than guessing (the field stays null).
_NATIONALITY_MAP = {
    "ESPANA": "ES", "ESTADOS UNIDOS": "US", "FRANCIA": "FR", "ARGENTINA": "AR",
    "SERBIA": "RS", "LITUANIA": "LT", "ITALIA": "IT", "ALEMANIA": "DE",
    "BRASIL": "BR", "NIGERIA": "NG", "SENEGAL": "SN", "CROACIA": "HR",
    "MONTENEGRO": "ME", "ESLOVENIA": "SI", "GRECIA": "GR", "PORTUGAL": "PT",
    "REINO UNIDO": "GB", "CANADA": "CA", "REPUBLICA DOMINICANA": "DO",
    "VENEZUELA": "VE", "MEXICO": "MX", "ANGOLA": "AO", "MALI": "ML",
    "BOSNIA Y HERZEGOVINA": "BA", "TURQUIA": "TR", "POLONIA": "PL",
    "PAISES BAJOS": "NL", "BELGICA": "BE", "UCRANIA": "UA", "GEORGIA": "GE",
    "CUBA": "CU", "PUERTO RICO": "PR", "COLOMBIA": "CO", "AUSTRALIA": "AU",
}


class ParserError(ValueError):
    """Raised when a page does not match the expected structure (spec §3.4).

    Failing loudly here prevents persisting corrupt or partial data when a
    source changes its markup.
    """


@dataclass
class ParsedGame:
    """A parsed game plus the teams and people it references.

    Attributes
    ----------
    game : NormalizedGame
        The normalized game with both teams' and all players' box scores.
    teams : list of NormalizedTeam
        The two teams, so the caller can upsert them before the game.
    persons : list of NormalizedPerson
        Every player appearing in the box score, so the caller can upsert them
        before the game (persistence resolves players by external id).
    """

    game: NormalizedGame
    teams: list[NormalizedTeam]
    persons: list[NormalizedPerson]


def parse_game_ids(html: str) -> list[str]:
    """Extract distinct finished-game ids from a results/calendar page.

    Parameters
    ----------
    html : str
        Raw HTML of ``resultados.aspx``.

    Returns
    -------
    list of str
        Game ids (the ``p`` parameter), de-duplicated, in document order.
    """
    seen: dict[str, None] = {}
    for match in _GAME_ID_RE.finditer(html):
        seen.setdefault(match.group(1), None)
    return list(seen.keys())


def parse_box_score(html: str, *, source: str, game_external_id: str) -> ParsedGame:
    """Parse a game box score (``Partido.aspx``) into a normalized game.

    Parameters
    ----------
    html : str
        Raw HTML of the box score page.
    source : str
        Connector id (e.g. "feb-primera") used for every ``ExternalRef``.
    game_external_id : str
        The game's ``p`` id, used as the game's external id.

    Returns
    -------
    ParsedGame
        The normalized game plus its two teams.

    Raises
    ------
    ParserError
        If the page does not contain exactly two box-score tables, a required
        column is missing, or no date can be found.
    """
    soup = BeautifulSoup(html, "lxml")
    tables = [t for t in soup.find_all("table") if _is_box_score_table(t)]
    if len(tables) != 2:
        raise ParserError(
            f"Expected 2 box-score tables, found {len(tables)} "
            f"(game {game_external_id})"
        )

    game_date = _parse_date(soup)

    teams: list[NormalizedTeam] = []
    team_boxes: list[NormalizedTeamBoxScore] = []
    player_boxes: list[NormalizedPlayerBoxScore] = []
    persons: list[NormalizedPerson] = []

    for table in tables:
        team, team_box, players, table_persons = _parse_team_table(
            table, source=source
        )
        teams.append(team)
        team_boxes.append(team_box)
        player_boxes.extend(players)
        persons.extend(table_persons)

    home, away = teams[0], teams[1]
    game = NormalizedGame(
        ref=ExternalRef(source=source, external_id=game_external_id),
        home_team_ref=home.ref,
        away_team_ref=away.ref,
        date=game_date,
        final_score_home=team_boxes[0].points,
        final_score_away=team_boxes[1].points,
        team_box_scores=team_boxes,
        player_box_scores=player_boxes,
    )
    return ParsedGame(game=game, teams=teams, persons=persons)


# -- Profile parsers (bio / branding / trajectory) --------------------------
#
# Player and team profile pages are server-rendered with label-keyed info blocks
# (`div.nodo` > `span.label` + `span.string`). Unlike the box score, missing
# *optional* fields do not raise — only an unrecognisable page (no name block /
# no info nodes) does — so a sparse profile still enriches what it can (§5.3).


def parse_player_profile(
    html: str, *, source: str, person_external_id: str
) -> NormalizedPersonProfile:
    """Parse a FEB player page (``/jugador/<i>/<c>``) into a bio profile.

    Parameters
    ----------
    html : str
        Raw HTML of the player profile page.
    source : str
        Connector id (e.g. "feb-primera") for every ``ExternalRef``.
    person_external_id : str
        The player's ``c`` id (our ``Person.external_id``) to enrich.

    Returns
    -------
    NormalizedPersonProfile
        Bio + trajectory. ``photo`` is always None (FEB carries no portrait).

    Raises
    ------
    ParserError
        If the page has no ``div.nombre`` name block (structural change).
    """
    soup = BeautifulSoup(html, "lxml")
    name_el = soup.find("div", class_="nombre")
    if name_el is None or not _clean(name_el.get_text()):
        raise ParserError("Player profile page missing the div.nombre name block")
    first, last = _split_name(_clean(name_el.get_text()))

    nodes = _nodo_map(soup)
    birth_date, birth_city = _parse_birth(nodes.get("Fecha Nacimiento", ""))
    return NormalizedPersonProfile(
        ref=ExternalRef(source=source, external_id=person_external_id),
        display_name=f"{first} {last}",
        birth_date=birth_date,
        birth_city=birth_city,
        nationality=_nationality(nodes.get("Nacionalidad")),
        height_cm=_ranged_int(nodes.get("Altura"), 120, 260),
        weight_kg=_ranged_int(nodes.get("Peso"), 40, 200),
        primary_position=_position(nodes.get("Puesto")),
        photo=None,  # FEB player pages expose no portrait image
        career=_parse_trajectory(
            soup, source=source, person_external_id=person_external_id
        ),
    )


def parse_team_profile(
    html: str, *, source: str, team_external_id: str
) -> NormalizedTeamProfile:
    """Parse a FEB team page (``/equipo/<i>``) into a branding profile.

    Parameters
    ----------
    html : str
        Raw HTML of the team profile page.
    source : str
        Connector id for every ``ExternalRef``.
    team_external_id : str
        The team's ``i`` id (our ``Team.external_id``) to enrich.

    Returns
    -------
    NormalizedTeamProfile
        Arena, city, website and the crest logo reference. Club colours are not
        cleanly available on FEB and are left blank (§5.3).

    Raises
    ------
    ParserError
        If the page has neither info nodes nor a crest image (structural change).
    """
    soup = BeautifulSoup(html, "lxml")
    nodes = _nodo_map(soup)
    if not nodes and soup.find("img", src=_LOGO_RE) is None:
        raise ParserError("Team profile page missing info nodes and crest image")

    arena = nodes.get("Nombre") or None  # first "Nombre" = pavilion section
    city = _city_from_address(nodes.get("Dirección"))
    website = nodes.get("Web") or None
    logo = NormalizedMediaRef(
        source=source,
        source_url=_LOGO_URL.format(i=team_external_id),
        license=_FEB_IMAGE_LICENSE,
        attribution=_FEB_IMAGE_ATTRIBUTION,
    )
    return NormalizedTeamProfile(
        ref=ExternalRef(source=source, external_id=team_external_id),
        arena=arena[:150] if arena else None,
        city=city[:100] if city else None,
        website=website[:200] if website and website.startswith("http") else None,
        logo=logo,
    )


def _nodo_map(soup) -> dict[str, str]:
    """Map ``div.nodo`` label text -> value text (first occurrence wins).

    Each info block is ``<div class="nodo"><span class="label">…</span>
    <span class="string">…</span></div>``. Keeping the first occurrence yields the
    bio block on player pages and the club (not pavilion) address on team pages.
    """
    out: dict[str, str] = {}
    for nodo in soup.find_all("div", class_="nodo"):
        label = nodo.find("span", class_="label")
        if label is None:
            continue
        key = _clean(label.get_text())
        value_el = nodo.find("span", class_="string")
        value = _clean(value_el.get_text()) if value_el else ""
        if key and key not in out:
            out[key] = value
    return out


def _parse_birth(value: str) -> tuple[date | None, str | None]:
    """Split a "DD/MM/YYYY City (Province)" cell into (birth_date, birth_city)."""
    value = _clean(value)
    if not value:
        return None, None
    match = _DATE_RE.search(value)
    birth_date: date | None = None
    rest = value
    if match:
        day, month, year, _h, _m = match.groups()
        try:
            birth_date = date(int(year), int(month), int(day))
        except ValueError:
            birth_date = None
        rest = value[match.end():]
    city = rest.split("(")[0].strip() or None
    return birth_date, city


def _nationality(value: str | None) -> str | None:
    """Map a Spanish country name to ISO alpha-2, or None if unrecognised."""
    if not value:
        return None
    return _NATIONALITY_MAP.get(_strip_accents(value).upper().strip())


def _position(value: str | None) -> str | None:
    """Map a Spanish "Puesto" to our 2-letter code, or None if unrecognised."""
    if not value:
        return None
    return _POSITION_MAP.get(_strip_accents(value).lower().strip())


def _ranged_int(text: str | None, low: int, high: int) -> int | None:
    """Return the first integer in ``text`` if within [low, high], else None."""
    if not text:
        return None
    match = re.search(r"\d+", text)
    if match is None:
        return None
    value = int(match.group())
    return value if low <= value <= high else None


def _parse_trajectory(
    soup, *, source: str, person_external_id: str
) -> list[NormalizedCareerEntry]:
    """Parse every "Trayectoria" table into career entries (Nacional + others).

    Each row maps season (``Temp.`` "19/20" -> "2019-2020"), category
    (``Categ.``) and ``Club [Equipo]`` (whose link, if present, gives the club's
    ``i`` so the entry can be linked to a known team). Entries are de-duplicated
    by external id.
    """
    entries: list[NormalizedCareerEntry] = []
    seen: set[str] = set()
    for table in soup.find_all("table"):
        column_index = _trajectory_header(table)
        if column_index is None:
            continue
        club_idx = column_index.get("Club [Equipo]")
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            texts = [_text(c) for c in cells]
            season = _season_label(_cell(texts, column_index, "Temp."))
            club = _cell(texts, column_index, "Club [Equipo]")
            if season is None or not club:
                continue
            team_ref = None
            if club_idx is not None and club_idx < len(cells):
                link = cells[club_idx].find("a", href=_TEAM_LINK_RE)
                if link is not None:
                    team_i = _TEAM_LINK_RE.search(link["href"]).group(1)
                    team_ref = ExternalRef(source=source, external_id=team_i)
            suffix = team_ref.external_id if team_ref else slugify(club)[:20]
            external_id = f"{person_external_id}:{season}:{suffix}"[:100]
            if external_id in seen:
                continue
            seen.add(external_id)
            league = _cell(texts, column_index, "Categ.") or None
            entries.append(
                NormalizedCareerEntry(
                    ref=ExternalRef(source=source, external_id=external_id),
                    season_label=season,
                    club_name=club[:150],
                    league_name=league[:100] if league else None,
                    team_ref=team_ref,
                )
            )
    return entries


def _trajectory_header(table) -> dict[str, int] | None:
    """Return a column index if the table is a trajectory table, else None."""
    for row in table.find_all("tr"):
        texts = [_text(c) for c in row.find_all(["th", "td"])]
        if "Temp." in texts and any("Club" in t for t in texts):
            index: dict[str, int] = {}
            for position, key in enumerate(texts):
                index.setdefault(key, position)
            return index
    return None


def _season_label(text: str) -> str | None:
    """Normalise a FEB "19/20" season cell into "2019-2020" (None if unparsable)."""
    match = re.match(r"(\d{2})\s*/\s*(\d{2})", _clean(text))
    if match is None:
        return None
    yy = int(match.group(1))
    start = 1900 + yy if yy >= 50 else 2000 + yy
    return f"{start}-{start + 1}"


def _city_from_address(address: str | None) -> str | None:
    """Extract the city from a "… <postal> City (Province)" address string."""
    if not address:
        return None
    match = re.search(r"\b\d{5}\b\s+(.+)", _clean(address))
    if match is None:
        return None
    return match.group(1).split("(")[0].strip() or None


def _strip_accents(text: str) -> str:
    """Return ``text`` with combining accents removed (for robust key lookup)."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def _is_box_score_table(table) -> bool:
    """Return True if a table looks like a player box score (has MIN & PT)."""
    headers = {_clean(th.get_text()) for th in table.find_all("th")}
    return "MIN" in headers and "PT" in headers and "TL" in headers


def _parse_team_table(
    table, *, source: str
) -> tuple[
    NormalizedTeam,
    NormalizedTeamBoxScore,
    list[NormalizedPlayerBoxScore],
    list[NormalizedPerson],
]:
    """Parse one team's box-score table into team + totals + players + persons."""
    column_index = _header_index(table)
    for required in ("MIN", "PT", "TC", "T3", "TL"):
        if required not in column_index:
            raise ParserError(f"Missing required column {required!r} in box score")

    team_name = _team_name(table)
    team_external_id: str | None = None
    player_boxes: list[NormalizedPlayerBoxScore] = []
    persons: list[NormalizedPerson] = []
    totals_cells: list[str] | None = None

    for row in _body_rows(table):
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        values = [_text(c) for c in cells]
        link = row.find("a", href=_PLAYER_LINK_RE)
        if link is None:
            if _is_totals_row(row):
                totals_cells = values
            continue

        team_id, player_id = _PLAYER_LINK_RE.search(link["href"]).groups()
        team_external_id = team_external_id or team_id
        player_boxes.append(
            _player_box(
                values,
                column_index,
                source=source,
                person_id=player_id,
                team_id=team_id,
            )
        )
        persons.append(
            _person(_text(link), source=source, person_id=player_id)
        )

    if team_external_id is None:
        raise ParserError("No player links found in box score table")
    if totals_cells is None:
        raise ParserError("No team totals row found in box score table")

    team_ref = ExternalRef(source=source, external_id=team_external_id)
    team = NormalizedTeam(
        ref=team_ref,
        name=team_name,
        short_name=team_name[:20],
        # FEB team ids are season-specific (a club gets a new id each season, and
        # sponsor prefixes change), so the slug includes source + id to stay
        # globally unique. Unifying a club's history across seasons would need a
        # canonical club mapping (documented follow-up).
        slug=slugify(f"{team_name}-{source}-{team_external_id}")[:60],
    )
    team_box = _team_box(totals_cells, column_index, team_ref)
    return team, team_box, player_boxes, persons


def _person(display_name: str, *, source: str, person_id: str) -> NormalizedPerson:
    """Build a normalized person from a "SURNAME, NAME" box-score label."""
    first, last = _split_name(display_name)
    return NormalizedPerson(
        ref=ExternalRef(source=source, external_id=person_id),
        first_name=first,
        last_name=last,
        slug=slugify(f"{first}-{last}-{source}-{person_id}")[:160],
    )


def _split_name(display_name: str) -> tuple[str, str]:
    """Split a "SURNAME(S), NAME" label into title-cased (first, last) names.

    Parameters
    ----------
    display_name : str
        Raw label as printed by FEB (e.g. "TAMBA VILLEN, ISMAEL").

    Returns
    -------
    tuple of str
        ``(first_name, last_name)``, each title-cased, never empty ("-" if so).
    """
    if "," in display_name:
        last_raw, first_raw = display_name.split(",", 1)
    else:
        last_raw, first_raw = display_name, display_name
    return (first_raw.strip().title() or "-", last_raw.strip().title() or "-")


def _player_box(
    values: list[str],
    column_index: dict[str, int],
    *,
    source: str,
    person_id: str,
    team_id: str,
) -> NormalizedPlayerBoxScore:
    """Build a player box score from a parsed table row."""
    fgm, fga = _shooting(_cell(values, column_index, "TC"))
    tpm, tpa = _shooting(_cell(values, column_index, "T3"))
    ftm, fta = _shooting(_cell(values, column_index, "TL"))
    return NormalizedPlayerBoxScore(
        person_ref=ExternalRef(source=source, external_id=person_id),
        team_ref=ExternalRef(source=source, external_id=team_id),
        minutes_played=_minutes(_cell(values, column_index, "MIN")),
        points=_int(_cell(values, column_index, "PT")),
        rebounds_off=_int(_cell(values, column_index, "RO")),
        rebounds_def=_int(_cell(values, column_index, "RD")),
        assists=_int(_cell(values, column_index, "AS")),
        steals=_int(_cell(values, column_index, "BR")),
        blocks=_int(_cell(values, column_index, "TF")),
        turnovers=_int(_cell(values, column_index, "BP")),
        fouls=_int(_cell(values, column_index, "FC")),
        field_goals_made=fgm,
        field_goals_att=fga,
        three_point_made=tpm,
        three_point_att=tpa,
        free_throws_made=ftm,
        free_throws_att=fta,
    )


def _team_box(
    values: list[str], column_index: dict[str, int], team_ref: ExternalRef
) -> NormalizedTeamBoxScore:
    """Build a team box score from the totals row."""
    fgm, fga = _shooting(_cell(values, column_index, "TC"))
    tpm, tpa = _shooting(_cell(values, column_index, "T3"))
    ftm, fta = _shooting(_cell(values, column_index, "TL"))
    return NormalizedTeamBoxScore(
        team_ref=team_ref,
        points=_int(_cell(values, column_index, "PT")),
        rebounds_off=_int(_cell(values, column_index, "RO")),
        rebounds_def=_int(_cell(values, column_index, "RD")),
        assists=_int(_cell(values, column_index, "AS")),
        steals=_int(_cell(values, column_index, "BR")),
        blocks=_int(_cell(values, column_index, "TF")),
        turnovers=_int(_cell(values, column_index, "BP")),
        fouls=_int(_cell(values, column_index, "FC")),
        field_goals_made=fgm,
        field_goals_att=fga,
        three_point_made=tpm,
        three_point_att=tpa,
        free_throws_made=ftm,
        free_throws_att=fta,
    )


def _header_index(table) -> dict[str, int]:
    """Map column header text -> index from the detail header row.

    FEB box scores have a two-row header: a grouping row (Rebotes/Tapones/Faltas
    spanning several columns) and a detail row with the per-column abbreviations.
    Only the detail row (the one containing ``MIN`` and ``PT``) aligns with the
    data rows, so the index is built from it. Duplicate headers (``TC`` appears
    for field goals and tapones-contra) keep the first occurrence.
    """
    for row in table.find_all("tr"):
        texts = [_text(c) for c in row.find_all(["th", "td"])]
        if "MIN" in texts and "PT" in texts:
            index: dict[str, int] = {}
            for position, key in enumerate(texts):
                index.setdefault(key, position)
            return index
    raise ParserError("No detail header row (with MIN/PT) found in box score")


def _body_rows(table):
    """Yield data rows (player and totals rows; skip header-only rows)."""
    body = table.find("tbody") or table
    for row in body.find_all("tr"):
        if row.find("th") and not row.find("td"):
            continue  # header-only row
        yield row


def _is_totals_row(row) -> bool:
    """Return True for the team totals row (``class="row-total"``)."""
    return any("total" in cls.lower() for cls in (row.get("class") or []))


def _text(node) -> str:
    """Return a node's text with sub-elements separated by spaces.

    Using a separator keeps glued values apart — e.g. a shooting cell
    ``3/4<span>75%</span>`` becomes ``"3/4 75%"`` rather than ``"3/475%"``.
    """
    return _clean(node.get_text(" "))


def _team_name(table) -> str:
    """Extract the team name from the table caption or a preceding heading."""
    caption = table.find("caption")
    if caption and _clean(caption.get_text()):
        return _clean(caption.get_text())
    heading = table.find_previous(["h1", "h2", "h3", "h4"])
    if heading and _clean(heading.get_text()):
        return _clean(heading.get_text())
    raise ParserError("Could not determine team name for box score table")


def _parse_date(soup) -> datetime:
    """Find a dd/mm/yyyy[ hh:mm] date anywhere on the page (timezone-aware)."""
    match = _DATE_RE.search(soup.get_text(" "))
    if match is None:
        raise ParserError("No game date found on box score page")
    day, month, year, hour, minute = match.groups()
    naive = datetime(
        int(year), int(month), int(day), int(hour or 0), int(minute or 0)
    )
    return timezone.make_aware(naive)


def _cell(values: list[str], column_index: dict[str, int], key: str) -> str:
    """Return the cell text for a header key, or empty string if out of range."""
    idx = column_index.get(key)
    if idx is None or idx >= len(values):
        return ""
    return values[idx]


def _clean(text: str) -> str:
    """Collapse whitespace and strip a cell's text."""
    return re.sub(r"\s+", " ", text or "").strip()


def _int(text: str) -> int:
    """Parse an integer cell, treating blanks/dashes as 0."""
    digits = re.sub(r"[^0-9-]", "", text or "")
    if digits in ("", "-"):
        return 0
    try:
        return max(int(digits), 0)
    except ValueError:
        return 0


def _minutes(text: str) -> int:
    """Parse a "mm:ss" minutes cell into whole minutes (blanks -> 0)."""
    text = _clean(text)
    if ":" in text:
        return _int(text.split(":", 1)[0])
    return _int(text)


def _shooting(text: str) -> tuple[int, int]:
    """Parse a "made/att pct%" shooting cell into (made, attempted)."""
    text = _clean(text)
    head = text.split(" ", 1)[0] if text else ""
    if "/" not in head:
        return 0, 0
    made_str, att_str = head.split("/", 1)
    return _int(made_str), _int(att_str)
