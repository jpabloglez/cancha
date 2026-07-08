"""URL routing for the versioned public API, mounted at ``/api/v1/`` (spec §5).

Resource collections are registered on a DRF router; the health check is a
standalone function view.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AllTimeLeadersView,
    GameViewSet,
    GlobalSearchView,
    LeadersView,
    LeagueViewSet,
    PersonViewSet,
    PlayerSeasonAggregateViewSet,
    SeasonViewSet,
    TeamSeasonViewSet,
    TeamViewSet,
    health,
)

router = DefaultRouter()
router.register("leagues", LeagueViewSet, basename="league")
router.register("seasons", SeasonViewSet, basename="season")
router.register("teams", TeamViewSet, basename="team")
router.register("team-seasons", TeamSeasonViewSet, basename="team-season")
router.register("players", PersonViewSet, basename="player")
router.register(
    "player-aggregates", PlayerSeasonAggregateViewSet, basename="player-aggregate"
)
router.register("games", GameViewSet, basename="game")

urlpatterns = [
    path("health/", health, name="health"),
    path("stats/leaders/", LeadersView.as_view(), name="leaders"),
    path("stats/alltime/", AllTimeLeadersView.as_view(), name="alltime-leaders"),
    path("search/", GlobalSearchView.as_view(), name="search"),
    path("", include(router.urls)),
]
