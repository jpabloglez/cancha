"""Django admin registrations for the players domain."""

from django.contrib import admin

from .models import (
    Person,
    PlayerGameStats,
    PlayerSeasonAggregate,
    RosterEntry,
    StaffEntry,
)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    """Admin listing for people (players and staff)."""

    list_display = ("first_name", "last_name", "nationality", "birth_date")
    search_fields = ("first_name", "last_name")
    prepopulated_fields = {"slug": ("first_name", "last_name")}


admin.site.register(RosterEntry)
admin.site.register(StaffEntry)
admin.site.register(PlayerGameStats)
admin.site.register(PlayerSeasonAggregate)
