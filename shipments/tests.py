from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from unittest import mock

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.utils import timezone

from actions.models import Action
from core.models import Customer, ShippingLine

from .models import SeaShipment
from .tracking import TrackingError, TrackingResult
from .tracking.dcsa import parse_events
from .tracking.service import refresh_shipment
from .validators import is_valid_container_number


class ContainerNumberTests(TestCase):
    def test_known_valid_numbers(self):
        for number in ["CSQU3054383", "MSKU9070323"]:
            self.assertTrue(is_valid_container_number(number), number)

    def test_invalid(self):
        self.assertFalse(is_valid_container_number("CSQU3054384"))
        self.assertFalse(is_valid_container_number("CSQ3054383"))
        self.assertTrue(is_valid_container_number("csqu 305438-3"))

    def test_model_normalizes(self):
        customer = Customer.objects.create(name="Test")
        s = SeaShipment.objects.create(customer=customer, container_number="csqu 305438 3", vessel_name="A", eta=timezone.now())
        self.assertEqual(s.container_number, "CSQU3054383")
        self.assertEqual(s.original_vessel_name, "A")
        self.assertIsNotNone(s.eta_original)


def event(classifier, when, location, vessel, imo, voyage, created=None):
    return {
        "eventType": "TRANSPORT",
        "eventClassifierCode": classifier,
        "transportEventTypeCode": "ARRI",
        "eventDateTime": when,
        "eventCreatedDateTime": created or when,
        "transportCall": {
            "UNLocationCode": location,
            "modeOfTransport": "VESSEL",
            "importVoyageNumber": voyage,
            "vessel": {"vesselName": vessel, "vesselIMONumber": imo},
        },
    }


class DCSAParseTests(TestCase):
    def test_picks_latest_estimate_at_pod_and_transshipment(self):
        events = [
            event("EST", "2026-10-02T08:00:00Z", "MAPTM", "FEEDER ONE", "1111111", "001N"),
            event("PLN", "2026-10-09T06:00:00Z", "NLRTM", "MAERSK HIDALGO", "9786786", "642W", "2026-09-20T00:00:00Z"),
            event("EST", "2026-10-10T14:00:00Z", "NLRTM", "MAERSK HIDALGO", "9786786", "642W", "2026-10-01T00:00:00Z"),
            {"eventType": "EQUIPMENT", "equipmentEventTypeCode": "LOAD"},
        ]
        result = parse_events(events, "NLRTM")
        self.assertEqual(result.vessel_name, "MAERSK HIDALGO")
        self.assertEqual(result.eta, datetime(2026, 10, 10, 14, tzinfo=dt_timezone.utc))
        self.assertIsNone(result.ata)
        self.assertEqual(result.vessels, ["FEEDER ONE", "MAERSK HIDALGO"])

    def test_actual_arrival_and_v3_shape(self):
        events = [{
            "eventClassifierCode": "ACT",
            "eventDateTime": "2026-10-10T16:30:00+02:00",
            "transportEvent": {"transportEventTypeCode": "ARRI"},
            "transportCall": {"location": {"UNLocationCode": "NLRTM"}, "vessel": {"vesselName": "EVER ACE", "vesselIMONumber": "9893890"}},
        }]
        result = parse_events(events, "NLRTM")
        self.assertEqual(result.vessel_name, "EVER ACE")
        self.assertIsNotNone(result.ata)

    def test_empty(self):
        self.assertIsNone(parse_events([], "NLRTM").eta)


class FakeProvider:
    name = "fake"

    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def track(self, shipment):
        if self.error:
            raise TrackingError(self.error)
        return self.result


class RefreshTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Klant")
        self.line = ShippingLine.objects.create(name="Maersk", scac="MAEU", tracking_provider="mock")
        self.eta = timezone.now() + timedelta(days=5)
        self.shipment = SeaShipment.objects.create(
            customer=self.customer, shipping_line=self.line, container_number="CSQU3054383", vessel_name="MAERSK HIDALGO", eta=self.eta
        )

    def run_with(self, provider):
        with mock.patch("shipments.tracking.service.get_provider", return_value=provider):
            return refresh_shipment(self.shipment)

    def test_vessel_change_is_flagged_and_creates_action(self):
        result = TrackingResult(provider="fake", eta=self.eta + timedelta(days=2), vessel_name="MSC GÜLSÜN", vessel_imo="9839430", voyage="X1")
        update = self.run_with(FakeProvider(result))
        self.shipment.refresh_from_db()
        self.assertTrue(update.vessel_changed and update.eta_changed)
        self.assertTrue(self.shipment.vessel_changed)
        self.assertEqual(self.shipment.vessel_name, "MSC GÜLSÜN")
        self.assertEqual(self.shipment.original_vessel_name, "MAERSK HIDALGO")
        self.assertEqual(self.shipment.eta_delay_hours, 48)
        self.assertTrue(Action.objects.filter(sea_shipment=self.shipment, title__contains="Schipwissel").exists())

    def test_small_eta_change_ignored_and_same_vessel(self):
        result = TrackingResult(provider="fake", eta=self.eta + timedelta(minutes=20), vessel_name="maersk hidalgo")
        update = self.run_with(FakeProvider(result))
        self.assertFalse(update.eta_changed or update.vessel_changed)

    def test_arrival_sets_status(self):
        result = TrackingResult(provider="fake", eta=self.eta, ata=self.eta, vessel_name="MAERSK HIDALGO")
        self.run_with(FakeProvider(result))
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.status, "aangekomen")

    def test_error_is_recorded(self):
        update = self.run_with(FakeProvider(error="API kapot"))
        self.shipment.refresh_from_db()
        self.assertFalse(update.success)
        self.assertEqual(self.shipment.tracking_last_error, "API kapot")

    def test_mock_provider_end_to_end(self):
        update = refresh_shipment(self.shipment)
        self.assertTrue(update.success)
        self.assertEqual(update.provider, "mock")

    def test_dcsa_provider_http(self):
        self.line.tracking_provider = "dcsa"
        self.line.api_base_url = "https://api.example.com/tnt/v2"
        self.line.save()
        payload = [event("EST", "2026-10-20T08:00:00Z", "NLRTM", "MAERSK HIDALGO", "9786786", "642W")]
        response = mock.Mock(status_code=200, json=lambda: payload)
        with mock.patch("shipments.tracking.dcsa.requests.get", return_value=response) as get:
            update = refresh_shipment(self.shipment)
        self.assertTrue(update.success)
        self.assertEqual(get.call_args.kwargs["params"]["equipmentReference"], "CSQU3054383")


class ShipmentViewTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Klant")

    def test_bulk_create_and_readonly_permissions(self):
        admin = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(admin)
        r = self.client.post("/zendingen/zeevracht/meerdere/", {"customer": self.customer.pk, "container_numbers": "CSQU3054383, MSKU9070323", "inspection_required": "on"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(SeaShipment.objects.count(), 2)
        r = self.client.post("/zendingen/zeevracht/meerdere/", {"customer": self.customer.pk, "container_numbers": "CSQU3054384"})
        self.assertContains(r, "Ongeldige containernummers")

        reader = User.objects.create_user("lezer", password="pw")
        reader.user_permissions.add(Permission.objects.get(codename="view_seashipment"))
        self.client.force_login(reader)
        self.assertEqual(self.client.get("/zendingen/zeevracht/").status_code, 200)
        self.assertEqual(self.client.get("/zendingen/zeevracht/nieuw/").status_code, 403)
        self.assertEqual(self.client.get("/beheer/klanten/").status_code, 403)


class OAuthProviderTests(TestCase):
    def test_bearer_token_is_fetched_and_cached(self):
        from django.core.cache import cache

        cache.clear()
        customer = Customer.objects.create(name="K")
        line = ShippingLine.objects.create(
            name="Maersk", scac="MAEU", tracking_provider="dcsa", api_base_url="https://api.example.com/tnt",
            oauth_token_url="https://api.example.com/oauth/token", oauth_client_id_env="T_ID", oauth_client_secret_env="T_SECRET",
            api_key_env="T_ID",
        )
        shipment = SeaShipment.objects.create(customer=customer, shipping_line=line, container_number="CSQU3054383")
        token_response = mock.Mock(status_code=200, json=lambda: {"access_token": "abc", "expires_in": 3600})
        events_response = mock.Mock(status_code=200, json=lambda: [])
        with mock.patch.dict("os.environ", {"T_ID": "id", "T_SECRET": "secret"}), \
                mock.patch("shipments.tracking.dcsa.requests.post", return_value=token_response) as post, \
                mock.patch("shipments.tracking.dcsa.requests.get", return_value=events_response) as get:
            refresh_shipment(shipment)
            refresh_shipment(shipment)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer abc")
        self.assertEqual(get.call_args.kwargs["headers"]["Consumer-Key"], "id")
