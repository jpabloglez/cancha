"""Django admin registrations for the ingestion domain."""

from django.contrib import admin

from .models import DataSource, IngestionRun, RawDocument


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    """Admin listing for external data sources."""

    list_display = ("name", "connector_id", "type", "base_url")


@admin.register(IngestionRun)
class IngestionRunAdmin(admin.ModelAdmin):
    """Admin listing for ingestion audit runs."""

    list_display = ("data_source", "started_at", "finished_at", "status", "records_processed")
    list_filter = ("status", "data_source")
    readonly_fields = ("started_at",)


@admin.register(RawDocument)
class RawDocumentAdmin(admin.ModelAdmin):
    """Admin listing for cached raw source documents."""

    list_display = ("source", "url", "status_code", "fetched_at")
    list_filter = ("source", "status_code")
    search_fields = ("url",)
    readonly_fields = ("fetched_at",)
