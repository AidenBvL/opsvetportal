from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from actions.models import Action
from planning.models import Employee, Shift
from shipments.models import SeaShipment
from shipments.tracking import TrackingResult
from shipments.tracking.service import refresh_shipment

from .models import Customer, NotificationPreference


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("dominic", email="dominic@example.com", password="pw", first_name="Dominic")
        self.employee = Employee.objects.create(name="Dominic Hylkema", user=self.user)
        self.boss = User.objects.create_user("raymond", email="raymond@example.com", password="pw")
        NotificationPreference.objects.create(user=self.boss, escalations=True, shipment_scope="all")
        self.customer = Customer.objects.create(name="Klant")

    def test_action_assigned_and_escalation(self):
        with self.captureOnCommitCallbacks(execute=True):
            action = Action.objects.create(title="Keuring regelen", owner=self.employee)
        self.assertEqual([m.to for m in mail.outbox], [["dominic@example.com"]])
        self.assertIn("Keuring regelen", mail.outbox[0].body)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            action.kind = Action.KIND_ESCALATION
            action.save()
        self.assertEqual([m.to for m in mail.outbox], [["raymond@example.com"]])
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            action.description = "update zonder nieuwe eigenaar of niveau"
            action.save()
        self.assertEqual(mail.outbox, [])

    def test_vessel_change_mails_handler_and_watchers(self):
        eta = timezone.now() + timedelta(days=4)
        shipment = SeaShipment.objects.create(customer=self.customer, container_number="CSQU3054383", vessel_name="A", eta=eta, handler=self.employee)
        provider = mock.Mock(name="p")
        provider.name = "fake"
        provider.track.return_value = TrackingResult(provider="fake", eta=eta + timedelta(days=1), vessel_name="B")
        with mock.patch("shipments.tracking.service.get_provider", return_value=provider), self.captureOnCommitCallbacks(execute=True):
            refresh_shipment(shipment)
        recipients = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(recipients, ["dominic@example.com", "raymond@example.com"])
        self.assertIn("Nu op:                B", mail.outbox[0].body)

    def test_eta_threshold(self):
        NotificationPreference.objects.create(user=self.user, eta_threshold_hours=24)
        eta = timezone.now() + timedelta(days=4)
        shipment = SeaShipment.objects.create(customer=self.customer, container_number="CSQU3054383", vessel_name="A", eta=eta, handler=self.employee)
        provider = mock.Mock()
        provider.name = "fake"
        provider.track.return_value = TrackingResult(provider="fake", eta=eta + timedelta(hours=6), vessel_name="A")
        with mock.patch("shipments.tracking.service.get_provider", return_value=provider), self.captureOnCommitCallbacks(execute=True):
            refresh_shipment(shipment)
        # Raymond: drempel 12u (standaard) → geen mail bij 6u; Dominic: drempel 24u → geen mail.
        self.assertEqual(mail.outbox, [])

    def test_daily_digest_and_shift_reminder(self):
        today = timezone.localdate()
        Action.objects.create(title="Te laat", owner=self.employee, due_date=today - timedelta(days=1))
        Shift.objects.create(date=today + timedelta(days=1), shift_type="avond", employee=self.employee)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("send_daily_mails", stdout=open("/dev/null", "w"))
        subjects = sorted(m.subject for m in mail.outbox)
        self.assertTrue(any("Dagoverzicht" in s for s in subjects), subjects)
        self.assertTrue(any("Morgen avonddienst" in s for s in subjects), subjects)

    def test_preferences_page(self):
        self.client.force_login(self.user)
        r = self.client.post("/beheer/mijn-meldingen/", {"shipment_scope": "all", "eta_threshold_hours": 6, "daily_digest": ""})
        self.assertEqual(r.status_code, 302)
        prefs = NotificationPreference.objects.get(user=self.user)
        self.assertEqual((prefs.shipment_scope, prefs.daily_digest, prefs.vessel_change), ("all", False, False))


class AuditLogTests(TestCase):
    def test_changes_are_logged_with_user(self):
        admin = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(admin)
        self.client.post("/beheer/klanten/nieuw/", {"name": "Fish BV", "city": "Rotterdam", "active": "on"})
        customer = Customer.objects.get()
        self.client.post(f"/beheer/klanten/{customer.pk}/bewerken/", {"name": "Fish BV", "city": "Barendrecht", "active": "on"})
        from .audit import history_for

        logs = list(reversed(history_for(customer)))
        self.assertEqual([log.action for log in logs], ["create", "update"])
        self.assertEqual(logs[1].user, admin)
        self.assertEqual(logs[1].changes, {"plaats": ["Rotterdam", "Barendrecht"]})
        page = self.client.get(f"/beheer/klanten/{customer.pk}/")
        self.assertContains(page, "Barendrecht")
        self.assertContains(self.client.get("/beheer/wijzigingslog/"), "Fish BV")

    def test_system_changes_have_no_user(self):
        customer = Customer.objects.create(name="X")
        from .audit import history_for

        self.assertIsNone(history_for(customer)[0].user)

    def test_roles_cannot_edit_log(self):
        call_command("setup_roles", stdout=open("/dev/null", "w"))
        from django.contrib.auth.models import Group

        for group in Group.objects.all():
            self.assertFalse(group.permissions.filter(codename__in=["change_auditlog", "delete_auditlog"]).exists(), group)
