"""Management command: sync CELERY_BEAT_SCHEDULE into the database.

``django-celery-beat``'s DatabaseScheduler reads periodic tasks from the
database rather than from ``settings.CELERY_BEAT_SCHEDULE``.  On a fresh
deployment Beat may not have started yet — running this command explicitly
creates or updates the ``PeriodicTask`` rows from the settings dict, so
scheduled tasks are active from the very first deploy without waiting for Beat
to start.

Re-running is safe: existing tasks are updated, nothing is deleted.

Examples
--------
``python manage.py sync_beat_schedule``
``python manage.py sync_beat_schedule --dry-run``
"""

import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask


class Command(BaseCommand):
    """Create or update PeriodicTask rows from CELERY_BEAT_SCHEDULE."""

    help = "Sync CELERY_BEAT_SCHEDULE settings into the django_celery_beat DB."

    def add_arguments(self, parser) -> None:
        """Register command-line options.

        Parameters
        ----------
        parser : argparse.ArgumentParser
            Parser provided by Django's command framework.
        """
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change without writing to the database.",
        )

    def handle(self, *args, **options) -> None:
        """Sync periodic tasks from settings.

        Parameters
        ----------
        *args
            Unused positional arguments.
        **options
            Parsed options; ``dry_run`` skips writes when True.
        """
        dry_run: bool = options["dry_run"]
        schedule: dict = getattr(settings, "CELERY_BEAT_SCHEDULE", {})

        if not schedule:
            self.stdout.write("CELERY_BEAT_SCHEDULE is empty — nothing to sync.")
            return

        created = 0
        updated = 0

        for name, entry in schedule.items():
            task_name: str = entry["task"]
            cron = entry.get("schedule")
            if cron is None:
                self.stderr.write(f"  Skipping {name}: no schedule defined.")
                continue

            # Extract crontab fields from a Celery crontab() object.
            minute = str(getattr(cron, "_orig_minute", "*"))
            hour = str(getattr(cron, "_orig_hour", "*"))
            day_of_week = str(getattr(cron, "_orig_day_of_week", "*"))
            day_of_month = str(getattr(cron, "_orig_day_of_month", "*"))
            month_of_year = str(getattr(cron, "_orig_month_of_year", "*"))

            kwargs_json = json.dumps(entry.get("kwargs", {}))
            args_json = json.dumps(list(entry.get("args", [])))

            self.stdout.write(
                f"  {'[dry-run] ' if dry_run else ''}{name}: "
                f"{task_name} at {minute} {hour} {day_of_week} {day_of_month} {month_of_year}"
            )

            if dry_run:
                continue

            crontab_obj, _ = CrontabSchedule.objects.get_or_create(
                minute=minute,
                hour=hour,
                day_of_week=day_of_week,
                day_of_month=day_of_month,
                month_of_year=month_of_year,
                timezone=str(settings.TIME_ZONE),
            )

            task, was_created = PeriodicTask.objects.get_or_create(
                name=name,
                defaults={
                    "task": task_name,
                    "crontab": crontab_obj,
                    "args": args_json,
                    "kwargs": kwargs_json,
                    "enabled": True,
                },
            )
            if was_created:
                created += 1
            else:
                changed = False
                if task.task != task_name:
                    task.task = task_name
                    changed = True
                if task.crontab_id != crontab_obj.pk:
                    task.crontab = crontab_obj
                    changed = True
                if task.kwargs != kwargs_json:
                    task.kwargs = kwargs_json
                    changed = True
                if changed:
                    task.save()
                    updated += 1

        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done: {created} created, {updated} updated, "
                    f"{len(schedule) - created - updated} unchanged."
                )
            )
