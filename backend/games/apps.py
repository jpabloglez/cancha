"""App configuration for the games domain (Game, TeamGameStats)."""

from django.apps import AppConfig


class GamesConfig(AppConfig):
    """Django app holding game and team-game-stat entities.

    Attributes
    ----------
    default_auto_field : str
        Primary key field type used for models in this app.
    name : str
        Python path of the application.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "games"
