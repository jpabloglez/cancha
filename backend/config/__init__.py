"""Django project package for the basketball statistics platform.

Ensures the Celery application is imported when Django starts so that the
``@shared_task`` decorator across apps uses the configured broker.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)
