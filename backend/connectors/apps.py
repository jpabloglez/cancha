"""App configuration for the connectors domain (source adapters)."""

from django.apps import AppConfig


class ConnectorsConfig(AppConfig):
    """Django app holding source-connector adapters (no models).

    Attributes
    ----------
    default_auto_field : str
        Primary key field type used for models in this app.
    name : str
        Python path of the application.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "connectors"
