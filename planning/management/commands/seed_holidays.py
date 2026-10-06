from django.core.management.base import BaseCommand
from django.utils import timezone

from planning.holidays import dutch_holidays
from planning.models import Holiday


class Command(BaseCommand):
    help = "Voeg Nederlandse feestdagen toe voor een of meer jaren."

    def add_arguments(self, parser):
        parser.add_argument("jaren", nargs="*", type=int)
        parser.add_argument("--zonder-bevrijdingsdag", action="store_true")

    def handle(self, *args, **options):
        years = options["jaren"] or [timezone.localdate().year, timezone.localdate().year + 1]
        n = 0
        for year in years:
            for day, name in dutch_holidays(year, include_liberation_day=not options["zonder_bevrijdingsdag"]):
                _, created = Holiday.objects.get_or_create(date=day, defaults={"name": name})
                n += created
        self.stdout.write(self.style.SUCCESS(f"{n} feestdagen toegevoegd."))
