"""Django admin registrations for the games domain."""

from django.contrib import admin

from .models import Game, TeamGameStats


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    """Admin listing for finished games."""

    list_display = (
        "date",
        "home_team_season",
        "away_team_season",
        "final_score_home",
        "final_score_away",
    )
    list_filter = ("season",)
    date_hierarchy = "date"


admin.site.register(TeamGameStats)
