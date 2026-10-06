from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from actions.models import Action
from core.models import Customer
from planning.models import Employee

from .models import MeetingBlock, MeetingItem


class MeetingFlowTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser("admin", "a@example.com", "pw"))
        self.andy = Employee.objects.create(name="Andy Salihi")
        self.dominic = Employee.objects.create(name="Dominic Hylkema")
        self.customer = Customer.objects.create(name="Klant")

    def add(self, block="ochtend", day="2026-10-09"):
        return self.client.post("/overleg/punt/nieuw/", {
            "datum": day, "block": block, f"{block}-title": "Wanneer wordt container X gekeurd?",
            f"{block}-raised_by": self.andy.pk, f"{block}-colleagues": [self.dominic.pk], f"{block}-customer": self.customer.pk,
        })

    def test_add_item_to_block_with_colleagues(self):
        self.add()
        item = MeetingItem.objects.get()
        self.assertEqual(item.meeting.block, "ochtend")
        self.assertEqual(list(item.colleagues.all()), [self.dominic])
        page = self.client.get("/overleg/?datum=2026-10-09")
        self.assertContains(page, "Wanneer wordt container X gekeurd?")

    def test_carry_over_end_of_day_goes_to_next_working_day(self):
        self.add(block="einde_dag", day="2026-10-09")  # vrijdag
        item = MeetingItem.objects.get()
        self.client.post(f"/overleg/punt/{item.pk}/actie/", {"action": "carry"})
        item.refresh_from_db()
        self.assertEqual(item.status, "doorgeschoven")
        new = MeetingItem.objects.exclude(pk=item.pk).get()
        self.assertEqual((new.meeting.date, new.meeting.block), (date(2026, 10, 12), "ochtend"))
        self.assertEqual(list(new.colleagues.all()), [self.dominic])

    def test_answer_and_convert_to_escalation(self):
        self.add()
        item = MeetingItem.objects.get()
        r = self.client.post(f"/overleg/punt/{item.pk}/actie/", {"action": "to_escalation"})
        action = Action.objects.get()
        self.assertRedirects(r, f"/acties/{action.pk}/bewerken/", fetch_redirect_response=False)
        self.assertEqual(action.kind, "escalatie")
        self.assertEqual(action.escalation_level, 1)
        self.assertEqual(action.owner, self.dominic)
        self.assertEqual(action.customer, self.customer)
        self.client.post(f"/overleg/punt/{item.pk}/actie/", {"action": "answered", "answer": "Morgen 10:00"})
        item.refresh_from_db()
        self.assertEqual((item.status, item.answer), ("beantwoord", "Morgen 10:00"))

    def test_block_attendees(self):
        self.client.post("/overleg/blok/opslaan/", {"datum": "2026-10-09", "block": "middag", "b-middag-attendees": [self.andy.pk], "b-middag-notes": "kort"})
        block = MeetingBlock.objects.get()
        self.assertEqual(list(block.attendees.all()), [self.andy])
