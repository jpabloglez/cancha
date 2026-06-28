"""App configuration for the teams domain (League, Season, Team, TeamSeason)."""

from django.apps import AppConfig


class TeamsConfig(AppConfig):
    """Django app holding competition and team entities.

    Attributes
    ----------
    default_auto_field : str
        Primary key field type used for models in this app.
    name : str
        Python path of the application.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "teams"
