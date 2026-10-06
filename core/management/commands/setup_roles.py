from django.core.management.base import BaseCommand

from core.roles import setup_roles


class Command(BaseCommand):
    help = "Maakt/actualiseert de standaardrollen (Beheerder, Planner, Operations, Alleen lezen)."

    def handle(self, *args, **options):
        names = setup_roles()
        self.stdout.write(self.style.SUCCESS(f"Rollen bijgewerkt: {', '.join(names)}"))
