from django.core.management.base import BaseCommand

from core import notifications


class Command(BaseCommand):
    help = "Verstuur het dagoverzicht en de herinneringen voor diensten van morgen."

    def handle(self, *args, **options):
        digest = notifications.daily_digest()
        reminders = notifications.shift_reminders()
        self.stdout.write(self.style.SUCCESS(f"{digest} dagoverzicht(en) en {reminders} dienstherinnering(en) verstuurd."))
