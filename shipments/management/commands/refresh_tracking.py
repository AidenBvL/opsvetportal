import time
from datetime import timedelta

from django.core.management.base import BaseCommand

from shipments.tracking.service import refresh_all


class Command(BaseCommand):
    help = "Haal de nieuwste ETA en het zeeschip op voor alle open containers."

    def add_arguments(self, parser):
        parser.add_argument("--loop", type=int, default=0, help="Blijf draaien en ververs elke N minuten.")
        parser.add_argument("--stale", type=int, default=0, help="Sla containers over die minder dan N minuten geleden gecontroleerd zijn.")

    def handle(self, *args, **options):
        while True:
            updates = refresh_all(stale_after=timedelta(minutes=options["stale"]))
            for u in updates:
                if u.message:
                    self.stdout.write(f"{u.shipment.container_number}: {u.message}")
            self.stdout.write(self.style.SUCCESS(f"{len(updates)} containers gecontroleerd."))
            if not options["loop"]:
                break
            time.sleep(options["loop"] * 60)
