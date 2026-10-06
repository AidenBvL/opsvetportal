import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Maak een beheerdersaccount uit DJANGO_ADMIN_USERNAME/EMAIL/PASSWORD als het nog niet bestaat."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_ADMIN_USERNAME")
        password = os.environ.get("DJANGO_ADMIN_PASSWORD")
        if not username or not password:
            self.stdout.write("DJANGO_ADMIN_USERNAME/PASSWORD niet gezet; overgeslagen.")
            return
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Beheerder {username} bestaat al.")
            return
        User.objects.create_superuser(username, os.environ.get("DJANGO_ADMIN_EMAIL", ""), password)
        self.stdout.write(self.style.SUCCESS(f"Beheerder {username} aangemaakt."))
