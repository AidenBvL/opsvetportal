from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.test import TestCase

from planning.models import Employee

from .models import Customer


class RolesAndAccountsTests(TestCase):
    def setUp(self):
        call_command("seed_portal", verbosity=0, stdout=open("/dev/null", "w"))
        self.admin = User.objects.create_superuser("admin", "a@example.com", "pw")

    def test_roles_created(self):
        self.assertEqual(set(Group.objects.values_list("name", flat=True)), {"Beheerder", "Planner", "Operations", "Alleen lezen"})
        ops = Group.objects.get(name="Operations").permissions
        self.assertTrue(ops.filter(codename="add_seashipment").exists())
        self.assertFalse(ops.filter(codename="delete_customer").exists())
        self.assertFalse(ops.filter(codename="change_shift").exists())
        self.assertTrue(ops.filter(codename="view_shift").exists())
        self.assertTrue(Group.objects.get(name="Planner").permissions.filter(codename="generate_roster").exists())
        self.assertFalse(Group.objects.get(name="Alleen lezen").permissions.exclude(codename__startswith="view_").exists())

    def test_create_account_with_role_extra_permission_and_employee(self):
        self.client.force_login(self.admin)
        ops = Group.objects.get(name="Operations")
        perm = Permission.objects.get(codename="generate_roster")
        aiden = Employee.objects.get(name="Aiden")
        r = self.client.post("/beheer/accounts/nieuw/", {
            "username": "aiden", "first_name": "Aiden", "email": "a@example.com", "is_active": "on",
            "password1": "Sterk-Wachtwoord-2026", "password2": "Sterk-Wachtwoord-2026",
            "groups": [ops.pk], "user_permissions": [perm.pk], "employee": aiden.pk,
        })
        self.assertEqual(r.status_code, 302)
        user = User.objects.get(username="aiden")
        self.assertTrue(user.check_password("Sterk-Wachtwoord-2026"))
        self.assertTrue(user.has_perm("planning.generate_roster"))
        self.assertTrue(user.has_perm("shipments.add_seashipment"))
        self.assertFalse(user.has_perm("core.delete_customer"))
        aiden.refresh_from_db()
        self.assertEqual(aiden.user, user)

    def test_user_management_requires_permission(self):
        reader = User.objects.create_user("lezer", password="pw")
        reader.groups.add(Group.objects.get(name="Alleen lezen"))
        self.client.force_login(reader)
        self.assertEqual(self.client.get("/beheer/accounts/").status_code, 403)
        self.assertEqual(self.client.get("/beheer/klanten/").status_code, 200)
        self.assertEqual(self.client.get("/beheer/klanten/nieuw/").status_code, 403)

    def test_login_required(self):
        r = self.client.get("/zendingen/zeevracht/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])


class CustomerTests(TestCase):
    def test_create_customer_and_detail(self):
        admin = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(admin)
        r = self.client.post("/beheer/klanten/nieuw/", {
            "name": "Fish & Co", "nationality": "Ecuadoraans", "street": "Calle 1", "city": "Guayaquil", "country": "Ecuador", "active": "on",
        })
        customer = Customer.objects.get(name="Fish & Co")
        self.assertRedirects(r, f"/beheer/klanten/{customer.pk}/")
        self.assertEqual(customer.address, "Calle 1, Guayaquil, Ecuador")
        self.assertContains(self.client.get(f"/beheer/klanten/{customer.pk}/"), "Ecuadoraans")

    def test_dashboard_renders_with_demo_data(self):
        call_command("seed_portal", "--demo", verbosity=0, stdout=open("/dev/null", "w"))
        admin = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(admin)
        self.assertContains(self.client.get("/"), "Aankomsten komende 7 dagen")


class PortTests(TestCase):
    def test_port_code_variants(self):
        from core.ports import port_code, port_label

        self.assertEqual(port_code("PARANAGUA (BR)"), "BRPNG")
        self.assertEqual(port_code("Paranaguá"), "BRPNG")
        self.assertEqual(port_code("Rotterdam, Netherlands"), "NLRTM")
        self.assertEqual(port_code("nl rtm"), "NLRTM")
        self.assertEqual(port_code("ANTWERP"), "BEANR")
        self.assertEqual(port_code("Manzanillo"), "Manzanillo")  # twee havens met die naam: niet raden
        self.assertEqual(port_code("MANZANILLO (MX)"), "MXZLO")
        self.assertEqual(port_code("Onbekende Haven"), "Onbekende Haven")
        self.assertEqual(port_code("Qingdao"), "CNQIN")  # twee codes, alleen CNQIN heeft terminals
        self.assertEqual(port_code("ITAJAI, BRAZIL"), "BRITJ")
        self.assertEqual(port_label("BRPNG"), "Paranaguá, Brazilië (BRPNG)")
        self.assertEqual(port_label("SGSIN"), "Singapore (SGSIN)")
        self.assertEqual(port_label("Onbekende Haven"), "Onbekende Haven")

    def test_new_port_recodes_open_shipments(self):
        from core.models import Port
        from shipments.models import SeaShipment

        customer = Customer.objects.create(name="K")
        shipment = SeaShipment.objects.create(customer=customer, container_number="CSQU3054383", port_of_loading="Nieuwe Testhaven")
        self.assertEqual(shipment.port_of_loading, "Nieuwe Testhaven")
        Port.objects.create(locode="XXPNV", name="Nieuwe Testhaven")
        shipment.refresh_from_db()
        self.assertEqual(shipment.port_of_loading, "XXPNV")


class TerminalTests(TestCase):
    def test_terminal_variants_become_full_name(self):
        from core.models import Port, Terminal
        from core.ports import terminal_name
        from shipments.models import SeaShipment

        from core.ports import terminal_label

        # Officiële SMDG-namen en -codes; varianten en afkortingen van rederijen worden herkend.
        self.assertEqual(terminal_name("ECT EUROMAX ROTTERDAM"), "ECT EUROMAX TERMINAL (EMX)")
        self.assertEqual(terminal_name("hutchison port delta ii"), "HUTCHISON DELTA II ROTTERDAM (HPD2)")
        self.assertEqual(terminal_name("TCP TER DE CONT DE PARANAGUA SA"), "TCP DE CONTEINERES DE PARANAGUA SA (TCP)")
        self.assertEqual(terminal_name("RWG"), "ROTTERDAM WORLD GATEWAY (RWG)")
        self.assertEqual(terminal_name("Onbekende kade"), "Onbekende kade")
        self.assertEqual(terminal_name("TERMINAL"), "TERMINAL")
        self.assertEqual(terminal_label("EMX"), "ECT EUROMAX TERMINAL (EMX) · Rotterdam, Nederland (NLRTM)")
        self.assertGreater(Terminal.objects.exclude(code="").count(), 1200)
        self.assertGreater(Port.objects.count(), 17000)
        customer = Customer.objects.create(name="K")
        shipment = SeaShipment.objects.create(customer=customer, container_number="CSQU3054383", terminal="KOELKADE NOORD")
        Terminal.objects.create(name="Koelkade Noord Vlissingen", code="KKN", port=Port.objects.get(locode="NLVLI"), aliases="KOELKADE NOORD")
        shipment.refresh_from_db()
        self.assertEqual(shipment.terminal, "Koelkade Noord Vlissingen (KKN)")

    def test_port_input_shows_full_name(self):
        from shipments.forms import SeaShipmentForm

        html = str(SeaShipmentForm(initial={"port_of_loading": "BRPNG"})["port_of_loading"])
        self.assertIn("Paranaguá, Brazilië", html)
        self.assertIn('<option value="NLRTM">Rotterdam, Nederland</option>', html)
