"""App configuration for the advanced statistics engine."""

from django.apps import AppConfig


class StatsConfig(AppConfig):
    """Django app holding the advanced metrics engine (no models).

    Attributes
    ----------
    default_auto_field : str
        Primary key field type used for models in this app.
    name : str
        Python path of the application.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "stats"
