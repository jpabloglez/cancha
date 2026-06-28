"""Root URL configuration.

Mounts the versioned public REST API under ``/api/v1/`` and the Django admin
under ``/admin/`` (spec §5.1).

Media files (logos, player photos) are served by Django's development static
helper. In production this responsibility moves to the web server (nginx/CDN).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("api.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
