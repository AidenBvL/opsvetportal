"""Eenvoudige planner voor Docker: tracking verversen, dagoverzicht en dienstherinneringen.

Gebruik: python manage.py run_scheduler   (blijft draaien)
Alternatief zonder deze planner: cronjobs voor `refresh_tracking` en `send_daily_mails`.
"""

import time
from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import JobRun


def due(name, interval=None, at=None):
    now = timezone.localtime()
    run = JobRun.objects.filter(name=name).first()
    if at is not None:
        hour, minute = (int(x) for x in at.split(":"))
        if (now.hour, now.minute) < (hour, minute):
            return False
        return run is None or timezone.localtime(run.last_run).date() < now.date()
    return run is None or now - run.last_run >= interval


def mark(name):
    JobRun.objects.update_or_create(name=name, defaults={"last_run": timezone.now()})


class Command(BaseCommand):
    help = "Draait geplande taken: tracking (elke N minuten) en de dagelijkse e-mails."

    def add_arguments(self, parser):
        parser.add_argument("--tracking-minuten", type=int, default=30)
        parser.add_argument("--once", action="store_true", help="Eén ronde uitvoeren en stoppen.")

    def handle(self, *args, **options):
        while True:
            if due("tracking", interval=timedelta(minutes=options["tracking_minuten"])):
                call_command("refresh_tracking", stdout=self.stdout)
                mark("tracking")
            if due("daily_mails", at=settings.DAILY_DIGEST_TIME):
                call_command("send_daily_mails", stdout=self.stdout)
                mark("daily_mails")
            if options["once"]:
                break
            time.sleep(60)
