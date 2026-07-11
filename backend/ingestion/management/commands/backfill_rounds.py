"""Management command: backfill round labels for already-ingested games.

Re-reads cached raw documents (calendar pages for FEB, round API responses for
ACB) and patches ``games.Game.round`` without re-fetching box scores.  Safe to
run multiple times — each execution overwrites with the same value.

Examples
--------
``python manage.py backfill_rounds``           # FEB + ACB
``python manage.py backfill_rounds --source feb``
``python manage.py backfill_rounds --source acb``
"""

import json
import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from connectors.parsers.acb import parse_matches
from connectors.parsers.feb import parse_game_round_map
from games.models import Game
from ingestion.models import RawDocument

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Patch Game.round for games whose round was never set on ingestion."""

    help = "Backfill round labels for already-ingested games from cached pages."

    def add_arguments(self, parser) -> None:
        """Register command-line options.

        Parameters
        ----------
        parser : argparse.ArgumentParser
            Parser provided by Django's command framework.
        """
        parser.add_argument(
            "--source",
            choices=["feb", "acb", "all"],
            default="all",
            help="Which source to patch (default: all).",
        )

    def handle(self, *args, **options) -> None:
        """Execute the backfill.

        Parameters
        ----------
        args : tuple
            Unused positional arguments from Django's command framework.
        options : dict
            Parsed options dict; ``source`` selects which connector to patch.
        """
        source = options["source"]
        if source in ("feb", "all"):
            self._patch_feb()
        if source in ("acb", "all"):
            self._patch_acb()

    def _patch_feb(self) -> None:
        """Patch FEB games using cached calendar pages.

        The calendar HTML is already stored in ``ingestion_rawdocument`` from
        the initial ingestion run; no new network requests are made here.
        """
        cal_docs = RawDocument.objects.filter(
            source__in=("feb-primera", "feb-segunda"),
        ).exclude(url__contains="/partido/").exclude(url__contains="/jugador/")

        total_updated = 0
        for doc in cal_docs:
            game_round = parse_game_round_map(doc.content)
            if not game_round:
                continue
            with transaction.atomic():
                for ext_id, round_label in game_round.items():
                    updated = Game.objects.filter(
                        source=doc.source,
                        external_id=ext_id,
                        round__isnull=True,
                    ).update(round=round_label)
                    total_updated += updated

        self.stdout.write(
            self.style.SUCCESS(f"FEB: updated {total_updated} games with round labels.")
        )

    def _patch_acb(self) -> None:
        """Patch ACB games using cached per-round schedule responses.

        Every per-round API fetch produces a document with ``availableFilters``
        (round id → round number map) and ``selectedFilters.round`` (the round
        that was fetched).  We derive the round label from these two fields and
        patch any games whose ``round`` is still null.
        """
        acb_docs = RawDocument.objects.filter(source="acb")
        total_updated = 0
        for doc in acb_docs:
            try:
                payload = json.loads(doc.content)
            except (json.JSONDecodeError, TypeError):
                continue
            if "availableFilters" not in payload:
                continue
            selected = payload.get("selectedFilters", {})
            round_id = selected.get("round")
            is_round_selected = selected.get("isRoundSelected", False)
            if not is_round_selected or round_id is None:
                # Skip the full-season schedule document (isRoundSelected=False).
                continue

            parsed = parse_matches(payload, source="acb")
            round_number = parsed.round_number_by_id.get(int(round_id))
            if round_number is None:
                continue
            round_label = f"J{round_number}"
            for header in parsed.headers:
                with transaction.atomic():
                    updated = Game.objects.filter(
                        source="acb",
                        external_id=header.external_id,
                        round__isnull=True,
                    ).update(round=round_label)
                    total_updated += updated

        self.stdout.write(
            self.style.SUCCESS(f"ACB: updated {total_updated} games with round labels.")
        )
