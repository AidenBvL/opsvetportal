"""Geplande taken via een URL, voor gratis hosting zonder achtergrondproces.

Een externe cronservice (bijv. cron-job.org of een GitHub Actions-schedule) roept elke
10-15 minuten /cron/<CRON_TOKEN>/ aan. Dat houdt de gratis server ook wakker.
"""

import io
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.http import Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .management.commands.run_scheduler import due, mark


@csrf_exempt
def run(request, token):
    if not settings.CRON_TOKEN or not secrets.compare_digest(token, settings.CRON_TOKEN):
        raise Http404
    ran = []
    out = io.StringIO()
    if due("tracking", interval=timedelta(minutes=30)):
        call_command("refresh_tracking", stdout=out)
        mark("tracking")
        ran.append("tracking")
    if due("daily_mails", at=settings.DAILY_DIGEST_TIME):
        call_command("send_daily_mails", stdout=out)
        mark("daily_mails")
        ran.append("daily_mails")
    return JsonResponse({"ran": ran, "log": out.getvalue().splitlines()[-20:]})
