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
