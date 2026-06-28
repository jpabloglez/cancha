"""Celery application bootstrap.

Defines the project-wide Celery app used by the asynchronous ingestion
pipeline. Scheduled tasks are programmed through Celery Beat using the
database scheduler (spec §3.3).
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("basketball_stats")

# Read configuration from Django settings using the CELERY_ namespace.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py modules across all installed apps.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> None:
    """Trivial task used to verify the worker is wired correctly.

    Parameters
    ----------
    self : celery.Task
        Bound task instance injected by Celery.

    Returns
    -------
    None
        Prints the request context for debugging.
    """
    print(f"Request: {self.request!r}")
