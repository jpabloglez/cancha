"""App configuration for the public REST API layer."""

from django.apps import AppConfig


class ApiConfig(AppConfig):
    """Django app exposing the versioned public REST API (no models).

    Attributes
    ----------
    default_auto_field : str
        Primary key field type used for models in this app.
    name : str
        Python path of the application.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
