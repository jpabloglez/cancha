"""Scrape FEB team logos from www.feb.es standings pages.

Discovers team logos from the official FEB standings pages (primerafeb and
segundafeb). Logos are served from ``imagenes.feb.es`` — a public CDN with no
authentication required. Results are persisted as ``MediaAsset`` records and
optionally downloaded.

Notes
-----
The CDN URL pattern is ``https://imagenes.feb.es/Imagen.aspx?i={id}&ti=1``.
The ``i`` parameter is specific to ``www.feb.es`` and differs from the
``external_id`` we store (which comes from ``baloncestoenvivo.feb.es``).
Matching therefore relies on normalised team names, not on IDs.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from connectors.http import RateLimitedClient
from ingestion.media import download_media_asset
from ingestion.persistence import upsert_media_asset
from ingestion.schemas import NormalizedMediaRef
from teams.models import MediaAsset, Team

logger = logging.getLogger(__name__)

#: Standings pages to scrape, keyed by FEB connector id.
_STANDINGS_PAGES: dict[str, str] = {
    "feb-primera": "https://www.feb.es/primerafeb/clasificacion.aspx",
    "feb-segunda": "https://www.feb.es/segundafeb/clasificacion.aspx",
}

_LOGO_CDN_HOST = "imagenes.feb.es"

#: Minimum fuzzy-match ratio to accept a team name match (0–1).
_MATCH_THRESHOLD = 0.55


@dataclass
class _LogoRef:
    """Scraped team name + CDN logo URL pair.

    Attributes
    ----------
    team_name : str
        Team name as printed on the FEB standings page.
    logo_url : str
        Absolute URL of the team logo on ``imagenes.feb.es``.
    """

    team_name: str
    logo_url: str


@dataclass
class FebLogoResult:
    """Summary of one scraper run.

    Attributes
    ----------
    connector_id : str
        The FEB connector (``feb-primera`` / ``feb-segunda``) that was scraped.
    logos_found : int
        Number of logo URLs discovered on the standings page.
    teams_matched : int
        Number of DB teams successfully matched to a logo.
    assets_created : int
        ``MediaAsset`` records created or updated.
    media_stored : int
        Binaries actually downloaded (only when ``store_media=True``).
    unmatched : list[str]
        Team names from the page that could not be matched to any DB team.
    """

    connector_id: str
    logos_found: int = 0
    teams_matched: int = 0
    assets_created: int = 0
    media_stored: int = 0
    unmatched: list[str] = field(default_factory=list)


# ── Text normalisation ────────────────────────────────────────────────────────


def _normalise(text: str) -> str:
    """Return lowercase, accent-stripped, punctuation-free text for matching.

    Parameters
    ----------
    text : str
        Raw team name as seen in a data source.

    Returns
    -------
    str
        Normalised representation suitable for fuzzy comparison.
    """
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]+", " ", ascii_text.lower()).strip()


def _similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two team names.

    Parameters
    ----------
    a : str
        First team name (raw or normalised).
    b : str
        Second team name.

    Returns
    -------
    float
        SequenceMatcher ratio in [0, 1].
    """
    return SequenceMatcher(None, _normalise(a), _normalise(b)).ratio()


# ── HTML scraping ─────────────────────────────────────────────────────────────


def _absolute_url(src: str, base: str) -> str:
    """Resolve a potentially protocol-relative or root-relative URL.

    Parameters
    ----------
    src : str
        URL attribute value from the ``<img>`` tag.
    base : str
        Base URL of the page being scraped (used for root-relative resolution).

    Returns
    -------
    str
        Absolute URL ready to fetch.
    """
    if src.startswith("//"):
        return "https:" + src
    parsed = urlparse(src)
    if parsed.scheme:
        return src
    return urljoin(base, src)


def _find_team_name_near_img(img: Tag) -> str | None:
    """Extract the team name closest to a logo ``<img>`` in the DOM tree.

    Walks up to the nearest row-level ancestor (``<tr>``, ``<li>``, ``<div>``
    with a role, or any direct parent whose tag appears list/row-like), then
    collects text from sibling cells/links. Returns the longest candidate that
    looks like a proper name (>3 chars, no pure-digit strings).

    Parameters
    ----------
    img : Tag
        The ``<img>`` BeautifulSoup element whose logo URL was found.

    Returns
    -------
    str or None
        Best candidate team name, or ``None`` when nothing suitable was found.
    """
    _ROW_TAGS = {"tr", "li"}

    # Walk up until we find a row-like element or exhaust 8 levels.
    node: Tag | None = img.parent
    for _ in range(8):
        if node is None:
            break
        if node.name in _ROW_TAGS:
            break
        node = node.parent  # type: ignore[assignment]

    if node is None:
        # Fall back to alt attribute.
        return (img.get("alt", "") or "").strip() or None

    # Collect all non-trivial text nodes from children.
    candidates: list[str] = []
    for child in node.descendants:
        if hasattr(child, "get_text"):
            continue  # skip Tag; we want NavigableString pieces indirectly
        text = str(child).strip()
        if len(text) > 3 and not text.isdigit():
            candidates.append(text)

    # Also try full text of <a> and <td>/<span> children.
    for tag in node.find_all(["a", "td", "span", "p"]):
        text = tag.get_text(separator=" ", strip=True)
        if len(text) > 3 and not text.isdigit():
            candidates.append(text)

    if not candidates:
        return (img.get("alt", "") or "").strip() or None

    # Prefer the longest candidate that doesn't look like a number or URL.
    candidates.sort(key=lambda s: -len(s))
    for c in candidates:
        if re.search(r"[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ]", c):
            # Trim whitespace and collapse internal spaces.
            clean = re.sub(r"\s+", " ", c).strip()
            if len(clean) > 3:
                return clean

    return (img.get("alt", "") or "").strip() or None


def _scrape_logos(url: str, client: RateLimitedClient) -> list[_LogoRef]:
    """GET a FEB standings page and return all discoverable logo refs.

    Parameters
    ----------
    url : str
        Absolute URL of the standings page (``/clasificacion.aspx`` variant).
    client : RateLimitedClient
        Rate-limited HTTP client to reuse.

    Returns
    -------
    list[_LogoRef]
        Pairs of (team_name, absolute_logo_url); may be empty on parse failure.
    """
    response = client.get(url)
    soup = BeautifulSoup(response.text, "lxml")

    refs: list[_LogoRef] = []
    seen_urls: set[str] = set()

    for img in soup.find_all("img"):
        src: str = img.get("src", "") or ""
        if _LOGO_CDN_HOST not in src:
            continue
        abs_url = _absolute_url(src, url)
        if abs_url in seen_urls:
            continue
        seen_urls.add(abs_url)

        team_name = _find_team_name_near_img(img)
        if team_name:
            refs.append(_LogoRef(team_name=team_name, logo_url=abs_url))
            logger.debug("Scraped logo: %r -> %s", team_name, abs_url)
        else:
            logger.debug("Logo found but no team name near %s", abs_url)

    return refs


# ── DB matching ───────────────────────────────────────────────────────────────


def _best_team_match(
    scraped_name: str, candidates: list[Team]
) -> Team | None:
    """Find the best matching ``Team`` row for a scraped name.

    Parameters
    ----------
    scraped_name : str
        Team name as returned by the standings page parser.
    candidates : list[Team]
        Pool of ``Team`` ORM objects to search (pre-filtered by source).

    Returns
    -------
    Team or None
        Best match when its similarity ratio exceeds ``_MATCH_THRESHOLD``,
        otherwise ``None``.
    """
    best_score = 0.0
    best_team: Team | None = None
    for team in candidates:
        score = _similarity(scraped_name, team.name)
        if score > best_score:
            best_score = score
            best_team = team

    if best_score >= _MATCH_THRESHOLD:
        logger.debug(
            "Matched %r -> %r (score=%.2f)", scraped_name, best_team.name, best_score  # type: ignore[union-attr]
        )
        return best_team

    logger.warning(
        "No match for %r (best=%.2f, threshold=%.2f)",
        scraped_name,
        best_score,
        _MATCH_THRESHOLD,
    )
    return None


# ── Main entry point ──────────────────────────────────────────────────────────


def fetch_feb_logos(
    connector_id: str,
    *,
    store_media: bool = True,
    client: RateLimitedClient | None = None,
) -> FebLogoResult:
    """Scrape FEB logos for one competition and persist as ``MediaAsset`` records.

    Teams are matched by name fuzzy-matching against all ``Team`` rows for the
    given ``connector_id`` source. A single asset is created per unique logo URL
    (keyed by ``source_url``), then linked to every ``Team`` row that matched.
    The binary is downloaded when ``store_media`` is ``True`` and
    ``settings.INGEST_STORE_MEDIA`` is enabled.

    Parameters
    ----------
    connector_id : str
        Must be ``"feb-primera"`` or ``"feb-segunda"``.
    store_media : bool
        Whether to trigger ``download_media_asset`` for newly created assets.
    client : RateLimitedClient or None
        HTTP client to reuse; a polite default is created and closed if omitted.

    Returns
    -------
    FebLogoResult
        Counts for reporting.

    Raises
    ------
    ValueError
        If ``connector_id`` is not a recognised FEB connector.
    """
    if connector_id not in _STANDINGS_PAGES:
        raise ValueError(
            f"Unknown connector {connector_id!r}; expected one of "
            f"{list(_STANDINGS_PAGES)}"
        )

    result = FebLogoResult(connector_id=connector_id)
    owns_client = client is None
    client = client or RateLimitedClient(min_interval_seconds=1.5)

    try:
        url = _STANDINGS_PAGES[connector_id]
        logger.info("Scraping %s", url)
        refs = _scrape_logos(url, client)
        result.logos_found = len(refs)
        logger.info("Found %d logo refs on page", result.logos_found)

        if not refs:
            logger.warning(
                "No logos found on %s — page structure may have changed", url
            )
            return result

        # Load all teams for this source once; a team may appear many times
        # (once per season) so we collect unique names to avoid redundant work.
        db_teams = list(Team.objects.filter(source=connector_id))
        logger.info("Loaded %d team rows for %s", len(db_teams), connector_id)

        # name -> list[Team] for efficient bulk-link after matching.
        from collections import defaultdict
        name_to_teams: dict[str, list[Team]] = defaultdict(list)
        for team in db_teams:
            name_to_teams[team.name].append(team)

        # Unique DB teams to match against (deduplicated by name).
        unique_by_name: list[Team] = [teams[0] for teams in name_to_teams.values()]

        processed_urls: set[str] = set()

        for ref in refs:
            if ref.logo_url in processed_urls:
                continue

            matched = _best_team_match(ref.team_name, unique_by_name)
            if matched is None:
                result.unmatched.append(ref.team_name)
                continue

            # Create/update the MediaAsset (idempotent on source_url).
            media_ref = NormalizedMediaRef(
                source=connector_id,
                source_url=ref.logo_url,
                license="©FEB (free distribution)",
                attribution=f"Logo {matched.name} via imagenes.feb.es",
            )
            asset = upsert_media_asset(
                media_ref, kind=MediaAsset.Kind.TEAM_LOGO
            )
            result.assets_created += 1
            processed_urls.add(ref.logo_url)

            # Link asset to every Team row with this name (all seasons).
            all_teams_with_name = name_to_teams[matched.name]
            for team in all_teams_with_name:
                if team.logo_id != asset.pk:
                    team.logo = asset
                    team.save(update_fields=["logo"])

            result.teams_matched += 1
            logger.info(
                "Linked logo %s -> %d team row(s) named %r",
                ref.logo_url,
                len(all_teams_with_name),
                matched.name,
            )

            if store_media and download_media_asset(asset.pk, client=client):
                result.media_stored += 1

    finally:
        if owns_client:
            client.close()

    return result
