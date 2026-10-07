from django.core.management.base import BaseCommand

from core.models import Port, Terminal
from core.ports import import_reference_data, recode_shipments


class Command(BaseCommand):
    help = "Laadt/actualiseert alle zeehavens (UN/LOCODE) en terminals (SMDG) uit core/data/*.csv."

    def handle(self, *args, **options):
        import_reference_data(Port, Terminal, log=self.stdout.write)
        recode_shipments()
