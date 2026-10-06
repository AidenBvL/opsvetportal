from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from planning.services import RosterLocked, generate_month


class Command(BaseCommand):
    help = "Genereer het thuiswerk- en dienstrooster voor een maand (standaard: volgende maand)."

    def add_arguments(self, parser):
        parser.add_argument("--jaar", type=int)
        parser.add_argument("--maand", type=int)
        parser.add_argument("--force", action="store_true", help="Ook genereren als het rooster definitief is.")

    def handle(self, *args, **options):
        today = timezone.localdate()
        year = options["jaar"] or (today.year + (1 if today.month == 12 else 0))
        month = options["maand"] or (1 if today.month == 12 else today.month + 1)
        try:
            roster, result = generate_month(year, month, force=options["force"])
        except RosterLocked as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Rooster {month:02d}-{year} gegenereerd."))
        for warning in result.warnings:
            self.stdout.write(self.style.WARNING(warning))
