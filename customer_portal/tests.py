from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings

from actions.models import Action, ExtraCost
from core.models import Customer, UserProfile
from shipments.models import SeaShipment


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", PORTAL_BASE_URL="https://portaal.example.nl")
class CustomerPortalTests(TestCase):
    def setUp(self):
        self.mine = Customer.objects.create(name="Mijn Klant")
        self.other = Customer.objects.create(name="Andere Klant")
        self.s1 = SeaShipment.objects.create(customer=self.mine, container_number="CSQU3054383", customer_reference="PO-1", notes="INTERN geheim")
        self.s2 = SeaShipment.objects.create(customer=self.other, container_number="MSKU9070323", customer_reference="PO-2")
        a = Action.objects.create(title="Interne actie", customer=self.mine, sea_shipment=self.s1)
        ExtraCost.objects.create(action=a, description="Kosten", amount=100, responsibility="klant")
        self.admin = User.objects.create_superuser("admin", "a@example.com", "pw")

    def make_customer_user(self):
        user = User.objects.create_user("klant@example.com", password="pw")
        UserProfile.objects.create(user=user, customer=self.mine)
        return user

    def test_invite_flow(self):
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"/beheer/klanten/{self.mine.pk}/klantaccount/", {"first_name": "Piet", "email": "Piet@Klant.nl"})
        user = User.objects.get(username="piet@klant.nl")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.profile.customer, self.mine)
        self.assertEqual(mail.outbox[0].to, ["piet@klant.nl"])
        link = next(line for line in mail.outbox[0].body.splitlines() if "/accounts/reset/" in line)
        self.assertTrue(link.startswith("https://portaal.example.nl/accounts/reset/"))
        self.client.logout()
        path = link.replace("https://portaal.example.nl", "")
        r = self.client.get(path, follow=True)
        r = self.client.post(r.redirect_chain[-1][0], {"new_password1": "Sterk-Wachtwoord-2026", "new_password2": "Sterk-Wachtwoord-2026"})
        self.assertEqual(r.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.check_password("Sterk-Wachtwoord-2026"))

    def test_customer_sees_only_own_containers(self):
        self.client.force_login(self.make_customer_user())
        page = self.client.get("/klantportaal/")
        self.assertContains(page, "CSQU3054383")
        self.assertNotContains(page, "MSKU9070323")
        detail = self.client.get(f"/klantportaal/container/{self.s1.pk}/")
        self.assertContains(detail, "PO-1")
        self.assertNotContains(detail, "INTERN geheim")
        self.assertEqual(self.client.get(f"/klantportaal/container/{self.s2.pk}/").status_code, 404)

    def test_customer_is_locked_out_of_internal_pages(self):
        self.client.force_login(self.make_customer_user())
        for url in ["/", "/acties/", "/acties/kosten/", f"/zendingen/zeevracht/{self.s1.pk}/", "/beheer/accounts/", "/admin/"]:
            r = self.client.get(url)
            self.assertRedirects(r, "/klantportaal/", fetch_redirect_response=False, msg_prefix=url)

    def test_internal_user_has_no_portal(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/klantportaal/").status_code, 404)
        self.assertNotContains(self.client.get("/beheer/accounts/"), "klant@example.com")
