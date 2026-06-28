"""Django admin registrations for the teams domain."""

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import League, MediaAsset, Season, Team, TeamSeason


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    """Admin listing for leagues."""

    list_display = ("name", "slug", "level", "country")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    """Admin listing for seasons."""

    list_display = ("name", "league", "start_date", "end_date")
    list_filter = ("league",)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    """Admin listing for teams."""

    list_display = ("name", "short_name", "city", "founded_year")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(TeamSeason)
class TeamSeasonAdmin(admin.ModelAdmin):
    """Admin listing for team-season participations."""

    list_display = ("team", "season", "league")
    list_filter = ("league", "season")


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    """Admin for stored media (logos/photos): provenance + takedown control.

    This is the operational endpoint for a rights-holder takedown request
    (docs/team-member-enrichment-plan.md §3, §4.2): use the *take down* action to
    hide the asset, delete its stored binary and stop the download task from ever
    re-fetching it, while keeping the row for provenance. The ``taken_down`` flag
    is also editable inline for a quick hide without removing the file.
    """

    list_display = (
        "kind",
        "source",
        "source_url",
        "is_stored",
        "taken_down",
        "attribution",
        "fetched_at",
    )
    list_filter = ("kind", "source", "taken_down")
    search_fields = ("source_url", "attribution")
    list_editable = ("taken_down",)
    readonly_fields = ("checksum", "fetched_at")
    actions = ("take_down", "clear_takedown")

    @admin.display(boolean=True, description="Stored")
    def is_stored(self, obj: MediaAsset) -> bool:
        """Whether a binary is currently stored for this asset."""
        return bool(obj.file)

    @admin.action(description="Take down: hide, delete binary, block re-download")
    def take_down(self, request: HttpRequest, queryset: QuerySet[MediaAsset]) -> None:
        """Honour a takedown request on the selected assets.

        Sets ``taken_down``, deletes the stored binary and clears the checksum
        (so a future run with ``force`` still won't re-store it, since the flag
        blocks the download). The provenance row is retained.

        Parameters
        ----------
        request : django.http.HttpRequest
            The admin request.
        queryset : django.db.models.QuerySet
            The selected media assets.
        """
        count = 0
        for asset in queryset:
            asset.take_down()
            count += 1
        self.message_user(
            request, f"{count} asset(s) taken down and their binaries removed."
        )

    @admin.action(description="Clear takedown (allow display/download again)")
    def clear_takedown(
        self, request: HttpRequest, queryset: QuerySet[MediaAsset]
    ) -> None:
        """Clear the takedown flag so the asset may be re-fetched and shown.

        Parameters
        ----------
        request : django.http.HttpRequest
            The admin request.
        queryset : django.db.models.QuerySet
            The selected media assets.
        """
        updated = queryset.update(taken_down=False)
        self.message_user(request, f"{updated} asset(s) takedown cleared.")
