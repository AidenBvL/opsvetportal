from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Customer, InspectionPoint, RoadCarrier, ShippingLine
from core.roles import setup_roles
from planning.models import Department, Employee

# Overgenomen uit "Thuiswerk en dienstrooster sept-okt 2026".
DEPARTMENTS = ["Sales", "Transport", "Fresh", "VET", "OPS algemeen", "Management"]
TEAM = [
    # naam, functie, groepen, thuiswerkdagen, vrije dagen, dienstenpool, geen dienst op, voorkeursdagen
    ("Rob Goldenbelt", "Sales", ["Sales"], 1, set(), False, set(), {0}),
    ("Andy Salihi", "OPS Transport / LSI", ["Transport"], 1, set(), True, set(), {1}),
    ("Marco van Soest", "Sales / OPS supervisor Fresh", ["Sales", "Fresh"], 1, set(), False, set(), {2}),
    ("Thomas Den Boer", "OPS / escalatiepunt transport", ["Transport"], 1, set(), False, set(), {3}),
    ("Desley Van Den Noort", "OPS Fresh (4-daagse week, wo vrij)", ["Fresh"], 1, {2}, True, set(), {4}),
    ("Davy Van Stuwe", "OPS", ["OPS algemeen"], 1, set(), False, set(), {2}),
    ("Dominic Hylkema", "OPS VET", ["VET"], 1, set(), True, set(), {2}),
    ("Jarno Pelt", "VET supervisor", ["VET"], 2, set(), False, set(), {0, 4}),
    ("Raymond Van Lent", "OPS manager algeheel", ["Management"], 1, set(), True, set(), {0}),
    ("Mitchell De Jong", "Head of Cory Brothers Fresh & Frozen NL", ["Management"], 1, set(), True, set(), {3}),
    # Aiden: niet in het thuiswerkschema, wel diensten, nooit op maandag (schooldag).
    ("Aiden", "OPS", [], 0, set(), True, {0}, set()),
]
SHIPPING_LINES = [
    ("Maersk", "MAEU"), ("MSC", "MSCU"), ("CMA CGM", "CMDU"), ("Hapag-Lloyd", "HLCU"),
    ("ONE (Ocean Network Express)", "ONEY"), ("Evergreen", "EGLV"), ("COSCO", "COSU"), ("ZIM", "ZIMU"),
]  # fmt: skip


class Command(BaseCommand):
    help = "Vul het portaal met rollen, het team, rederijen en feestdagen. Met --demo ook voorbeelddossiers."

    def add_arguments(self, parser):
        parser.add_argument("--demo", action="store_true", help="Voeg voorbeeldklanten, -keurpunten en -dossiers toe.")

    def handle(self, *args, **options):
        setup_roles()
        departments = {name: Department.objects.get_or_create(name=name)[0] for name in DEPARTMENTS}
        for name, title, groups, wfh, off, pool, no_shift, pref in TEAM:
            employee, _ = Employee.objects.update_or_create(
                name=name,
                defaults={"job_title": title, "wfh_days_per_week": wfh, "days_off": off, "in_shift_pool": pool,
                          "no_shift_weekdays": no_shift, "preferred_wfh_weekdays": pref},
            )
            employee.departments.set([departments[g] for g in groups])
        for name, scac in SHIPPING_LINES:
            ShippingLine.objects.get_or_create(name=name, defaults={"scac": scac})
        call_command("seed_holidays", stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Basisgegevens geladen."))
        if options["demo"]:
            self.demo()

    def demo(self):
        from actions.models import Action, ExtraCost
        from shipments.models import RoadTransport, SeaShipment
        from shipments.validators import container_check_digit

        def container(prefix, serial):
            base = f"{prefix}{serial:06d}"
            return base + str(container_check_digit(base))

        point, _ = InspectionPoint.objects.get_or_create(
            name="Voorbeeld GCP Maasvlakte", defaults={"traces_code": "NLRTM4", "city": "Rotterdam", "opening_hours": "ma-vr 07:00-22:00"})
        InspectionPoint.objects.get_or_create(name="Voorbeeld GCP Eemhaven", defaults={"city": "Rotterdam"})
        carrier, _ = RoadCarrier.objects.get_or_create(name="Voorbeeld Koeltransport BV", defaults={"city": "Barendrecht"})
        customer, _ = Customer.objects.get_or_create(
            name="Voorbeeld Seafood Import BV", defaults={"nationality": "Nederlands", "city": "Rotterdam", "country": "Nederland"})
        customer2, _ = Customer.objects.get_or_create(
            name="Example Meat Trading Ltd", defaults={"nationality": "Brits", "city": "London", "country": "Verenigd Koninkrijk"})
        maersk = ShippingLine.objects.get(scac="MAEU")
        msc = ShippingLine.objects.get(scac="MSCU")
        now = timezone.now()
        for i, (cust, line, prefix) in enumerate([(customer, maersk, "MSKU"), (customer, msc, "MSCU"), (customer2, maersk, "MRKU"),
                                                  (customer2, msc, "MEDU")]):
            number = container(prefix, 123450 + i)
            SeaShipment.objects.get_or_create(
                container_number=number,
                defaults={"customer": cust, "shipping_line": line, "inspection_point": point, "customer_reference": f"PO-{4500 + i}",
                          "cory_reference": f"CBNL-26-{1000 + i}", "eta": now + timedelta(days=2 + i * 2), "vessel_name": "MAERSK HIDALGO" if line == maersk else "MSC GÜLSÜN",
                          "goods_description": "Frozen shrimps" if cust == customer else "Frozen beef", "temperature_setpoint": Decimal("-18.0"),
                          "free_time_until": (now + timedelta(days=6 + i)).date()},
            )
        first = SeaShipment.objects.order_by("pk").first()
        RoadTransport.objects.get_or_create(
            cory_reference="CBNL-26-1000-T", defaults={"customer": first.customer, "carrier": carrier, "sea_shipment": first,
                                                       "loading_place": "Maasvlakte terminal", "unloading_place": "Koelhuis Barendrecht",
                                                       "loading_at": first.eta + timedelta(days=1)})
        action, _ = Action.objects.get_or_create(
            title="Keuring niet op tijd aangemeld - extra plugin dagen",
            defaults={"kind": Action.KIND_ESCALATION, "priority": 3, "customer": first.customer, "sea_shipment": first,
                      "due_date": timezone.localdate() + timedelta(days=1), "escalation_level": 2})
        if not action.costs.exists():
            ExtraCost.objects.create(action=action, cost_type="opslag", description="2 dagen plugin terminal",
                                     amount=Decimal("185.00"), responsibility=ExtraCost.RESP_CARRIER)
        self.stdout.write(self.style.SUCCESS("Demodata geladen."))
