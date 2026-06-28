"""App configuration for the players domain (people, rosters, player stats)."""

from django.apps import AppConfig


class PlayersConfig(AppConfig):
    """Django app holding person, roster, staff and player-stat entities.

    Attributes
    ----------
    default_auto_field : str
        Primary key field type used for models in this app.
    name : str
        Python path of the application.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "players"
