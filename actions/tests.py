from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.models import Customer
from shipments.models import SeaShipment

from .models import Action, ExtraCost


class ActionTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser("admin", "a@example.com", "pw"))
        self.customer = Customer.objects.create(name="Klant")
        self.shipment = SeaShipment.objects.create(customer=self.customer, container_number="CSQU3054383")

    def test_cost_inherits_customer_and_shipment(self):
        action = Action.objects.create(title="Demurrage", customer=self.customer, sea_shipment=self.shipment)
        r = self.client.post(f"/acties/{action.pk}/kosten/", {
            "cost_type": "demurrage", "description": "3 dagen", "amount": "450.00", "currency": "EUR",
            "responsibility": "vervoerder", "status": "geclaimd",
        })
        self.assertEqual(r.status_code, 302)
        cost = ExtraCost.objects.get()
        self.assertEqual((cost.customer, cost.sea_shipment), (self.customer, self.shipment))
        self.assertEqual(action.total_costs, Decimal("450.00"))

    def test_cost_without_action_takes_customer_from_shipment(self):
        cost = ExtraCost.objects.create(sea_shipment=self.shipment, description="Keuring", amount=Decimal("95"), responsibility="klant")
        self.assertEqual(cost.customer, self.customer)

    def test_escalate_and_complete(self):
        action = Action.objects.create(title="Te laat", due_date=timezone.localdate() - timedelta(days=1))
        self.assertTrue(action.is_overdue)
        self.client.post(f"/acties/{action.pk}/status/", {"escalate": "1"})
        action.refresh_from_db()
        self.assertEqual((action.kind, action.escalation_level), ("escalatie", 1))
        self.client.post(f"/acties/{action.pk}/status/", {"escalate": "1"})
        action.refresh_from_db()
        self.assertEqual(action.escalation_level, 2)
        self.client.post(f"/acties/{action.pk}/status/", {"status": "gereed"})
        action.refresh_from_db()
        self.assertIsNotNone(action.completed_at)
        self.assertFalse(action.is_overdue)

    def test_dashboard_and_cost_export(self):
        a = Action.objects.create(title="Esc", kind="escalatie", escalation_level=3, customer=self.customer)
        ExtraCost.objects.create(action=a, description="Opslag", amount=Decimal("100"), responsibility="cory")
        page = self.client.get("/acties/")
        self.assertContains(page, "Esc")
        csv = self.client.get("/acties/kosten/?export=csv")
        self.assertIn("Wij (Cory Brothers)", csv.content.decode())
        listing = self.client.get("/acties/kosten/?responsibility=cory")
        self.assertEqual(listing.context["grand_total"], Decimal("100"))
