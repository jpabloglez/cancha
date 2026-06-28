"""App configuration for the ingestion domain (DataSource, IngestionRun)."""

from django.apps import AppConfig


class IngestionConfig(AppConfig):
    """Django app holding ingestion auditing entities and ETL tasks.

    Attributes
    ----------
    default_auto_field : str
        Primary key field type used for models in this app.
    name : str
        Python path of the application.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "ingestion"
