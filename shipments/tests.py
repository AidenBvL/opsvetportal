from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from unittest import mock

from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
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


@override_settings(TERMINAL49_API_KEY="test-key")
class Terminal49Tests(TestCase):
    def setUp(self):
        customer = Customer.objects.create(name="K")
        line = ShippingLine.objects.create(name="Maersk", scac="MAEU", tracking_provider="terminal49")
        self.shipment = SeaShipment.objects.create(customer=customer, shipping_line=line, container_number="CSQU3054383",
                                                   vessel_name="MAERSK HIDALGO", eta=timezone.now() + timedelta(days=3))

    @staticmethod
    def response(payload, status=200):
        return mock.Mock(status_code=status, json=lambda: payload, text=str(payload))

    def test_full_flow_request_pending_then_data(self):
        created = self.response({"data": {"id": "tr1", "type": "tracking_request", "attributes": {"status": "pending"}, "relationships": {}}}, 201)
        with mock.patch("shipments.tracking.terminal49.requests.request", return_value=created) as req:
            update = refresh_shipment(self.shipment)
        self.assertTrue(update.success)
        self.assertIn("Aangemeld bij Terminal49", update.message)
        method, url = req.call_args.args
        self.assertEqual((method, url), ("POST", "https://api.terminal49.com/v2/tracking_requests"))
        body = req.call_args.kwargs["json"]["data"]["attributes"]
        self.assertEqual(body, {"request_type": "container", "request_number": "CSQU3054383", "scac": "MAEU"})
        self.assertEqual(req.call_args.kwargs["headers"]["Authorization"], "Token test-key")
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.external_tracking_id, "tr:tr1")

        ready = self.response({"data": {"id": "tr1", "attributes": {"status": "created"},
                                        "relationships": {"tracked_object": {"data": {"id": "shp9", "type": "shipment"}}}}})
        shipment_payload = self.response({
            "data": {"id": "shp9", "attributes": {"pod_eta_at": "2026-10-20T06:00:00Z", "pod_vessel_name": "MSC GÜLSÜN",
                                                   "pod_vessel_imo": "9839430", "pod_voyage_number": "FL636R", "pod_ata_at": None}},
            "included": [{"type": "container", "attributes": {"number": "CSQU3054383", "pod_arrived_at": None}}],
        })
        with mock.patch("shipments.tracking.terminal49.requests.request", side_effect=[ready, shipment_payload]):
            update = refresh_shipment(self.shipment)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.external_tracking_id, "shp:shp9")
        self.assertTrue(update.vessel_changed)
        self.assertEqual(self.shipment.vessel_name, "MSC GÜLSÜN")
        self.assertEqual(self.shipment.voyage, "FL636R")

    def test_uses_bl_and_reports_bad_key(self):
        self.shipment.bl_number = "MAEU254123987"
        self.shipment.save()
        with mock.patch("shipments.tracking.terminal49.requests.request", return_value=self.response({"errors": []}, 403)) as req:
            update = refresh_shipment(self.shipment)
        self.assertEqual(req.call_args.kwargs["json"]["data"]["attributes"]["request_type"], "bill_of_lading")
        self.assertFalse(update.success)
        self.assertIn("403 bij POST /tracking_requests", update.message)

    def test_failed_request_is_reset(self):
        self.shipment.external_tracking_id = "tr:tr1"
        self.shipment.save()
        failed = self.response({"data": {"id": "tr1", "attributes": {"status": "failed", "failed_reason": "not_found"}, "relationships": {}}})
        with mock.patch("shipments.tracking.terminal49.requests.request", return_value=failed):
            update = refresh_shipment(self.shipment)
        self.shipment.refresh_from_db()
        self.assertFalse(update.success)
        self.assertEqual(self.shipment.external_tracking_id, "")

    @override_settings(TERMINAL49_API_KEY="")
    def test_missing_key(self):
        update = refresh_shipment(self.shipment)
        self.assertIn("TERMINAL49_API_KEY", update.message)


class CronEndpointTests(TestCase):
    @override_settings(CRON_TOKEN="geheim")
    def test_token_required_and_runs_jobs(self):
        self.assertEqual(self.client.get("/cron/fout/").status_code, 404)
        with mock.patch("core.cron.call_command") as call:
            r = self.client.get("/cron/geheim/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("tracking", r.json()["ran"])
        self.assertIn("refresh_tracking", [c.args[0] for c in call.call_args_list])

    @override_settings(CRON_TOKEN="")
    def test_disabled_without_token(self):
        self.assertEqual(self.client.get("/cron/x/").status_code, 404)


@override_settings(TERMINAL49_API_KEY="test-key")
class Terminal49ImprovementTests(TestCase):
    def setUp(self):
        customer = Customer.objects.create(name="K")
        line = ShippingLine.objects.create(name="Maersk", scac="MAEU", tracking_provider="terminal49")
        self.shipment = SeaShipment.objects.create(customer=customer, shipping_line=line, container_number="CSQU3054383",
                                                   eta=timezone.now() + timedelta(days=3))

    response = staticmethod(Terminal49Tests.response)

    def test_booking_number_preferred_over_container(self):
        self.shipment.booking_number = "254123987"
        self.shipment.save()
        pending = self.response({"data": {"id": "tr1", "attributes": {"status": "pending"}, "relationships": {}}}, 201)
        with mock.patch("shipments.tracking.terminal49.requests.request", return_value=pending) as req:
            refresh_shipment(self.shipment)
        attrs = req.call_args.kwargs["json"]["data"]["attributes"]
        self.assertEqual((attrs["request_type"], attrs["request_number"]), ("booking_number", "254123987"))

    def test_duplicate_reuses_existing_request(self):
        duplicate = self.response({"errors": [{"status": "422", "code": "duplicate", "detail": "already exists"}]}, 422)
        listing = self.response({"data": [
            {"id": "other", "attributes": {"request_number": "XXXX", "scac": "MAEU", "status": "created"}},
            {"id": "tr7", "attributes": {"request_number": "CSQU3054383", "scac": "MAEU", "status": "created"},
             "relationships": {"tracked_object": {"data": {"id": "shp7", "type": "shipment"}}}},
        ]})
        shipment_payload = self.response({"data": {"id": "shp7", "attributes": {"pod_eta_at": "2026-10-20T06:00:00Z"}}, "included": []})
        with mock.patch("shipments.tracking.terminal49.requests.request", side_effect=[duplicate, listing, shipment_payload]) as req:
            update = refresh_shipment(self.shipment)
        self.assertTrue(update.success, update.message)
        self.assertEqual(req.call_args_list[1].kwargs["params"], {"q": "CSQU3054383"})
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.external_tracking_id, "shp:shp7")

    def test_original_eta_discharge_and_last_free_day(self):
        self.shipment.external_tracking_id = "shp:shp9"
        self.shipment.free_time_until = None
        self.shipment.save()
        payload = self.response({
            "data": {"id": "shp9", "attributes": {"pod_eta_at": "2026-10-20T06:00:00Z", "pod_original_eta_at": "2026-10-18T06:00:00Z",
                                                   "pod_ata_at": "2026-10-20T07:00:00Z", "pod_vessel_name": "EVER ACE"}},
            "included": [{"type": "container", "attributes": {"number": "CSQU3054383", "pod_discharged_at": "2026-10-21T03:00:00Z",
                                                              "pickup_lfd": "2026-10-23T22:00:00Z"}}],
        })
        with mock.patch("shipments.tracking.terminal49.requests.request", return_value=payload):
            refresh_shipment(self.shipment)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.eta_original.isoformat(), "2026-10-18T06:00:00+00:00")
        self.assertEqual(self.shipment.eta_delay_hours, 49)
        self.assertIsNotNone(self.shipment.discharged_at)
        # 22:00 UTC is middernacht 24 oktober in Nederland (zomertijd).
        self.assertEqual(str(self.shipment.free_time_until), "2026-10-24")
        self.assertEqual(self.shipment.status, "aangekomen")


@override_settings(TERMINAL49_API_KEY="test-key")
class Terminal49ErrorMessageTests(TestCase):
    def test_401_on_get_names_endpoint_and_detail(self):
        customer = Customer.objects.create(name="K")
        line = ShippingLine.objects.create(name="CMA CGM", scac="CMDU", tracking_provider="terminal49")
        shipment = SeaShipment.objects.create(customer=customer, shipping_line=line, container_number="CSQU3054383",
                                              external_tracking_id="tr:abc")
        resp = mock.Mock(status_code=401, json=lambda: {"errors": [{"title": "Unauthorized", "detail": "Invalid token"}]}, text="")
        with mock.patch("shipments.tracking.terminal49.requests.request", return_value=resp):
            update = refresh_shipment(shipment)
        self.assertIn("401 bij GET /tracking_requests/abc", update.message)
        self.assertIn("Invalid token", update.message)


@override_settings(TERMINAL49_API_KEY="test-key")
class Terminal49FreePlanTests(TestCase):
    def test_free_plan_message(self):
        customer = Customer.objects.create(name="K")
        line = ShippingLine.objects.create(name="CMA CGM", scac="CMDU", tracking_provider="terminal49")
        shipment = SeaShipment.objects.create(customer=customer, shipping_line=line, container_number="CSQU3054383",
                                              external_tracking_id="tr:abc")
        detail = "You do not have permissions for using the API, except for creating tracking requests. All other permissions require a paid plan."
        resp = mock.Mock(status_code=401, json=lambda: {"errors": [{"detail": detail}]}, text="")
        with mock.patch("shipments.tracking.terminal49.requests.request", return_value=resp):
            update = refresh_shipment(shipment)
        self.assertIn("gratis plan", update.message)
        self.assertNotIn("ongeldig", update.message)


class SameVesselTests(TestCase):
    def test_name_variants_and_imo(self):
        from .tracking.service import same_vessel

        self.assertTrue(same_vessel("COSCO GEMINI", "COSCO SHIPPING GEMINI"))
        self.assertTrue(same_vessel("MSC Gülsün", "MSC GÜLSÜN"))
        self.assertFalse(same_vessel("MAERSK HIDALGO", "MSC GÜLSÜN"))
        self.assertFalse(same_vessel("COSCO GEMINI", "COSCO GEMINI", "9783538", "9123456"))
        self.assertTrue(same_vessel("A", "B", "9783538", "9783538"))


SAFECUBE_SAMPLE = {
    "metadata": {"shipmentType": "BL", "shipmentNumber": "QGD3466869", "sealine": "CMDU", "shippingStatus": "IN_TRANSIT"},
    "route": {
        "pol": {"location": {"name": "Qingdao", "locode": "CNQDG"}, "date": "2026-09-24T08:00:00Z", "actual": True, "predictiveEta": None},
        "pod": {"location": {"name": "Rotterdam", "locode": "NLRTM"}, "date": "2026-11-03T07:00:00Z", "actual": False, "predictiveEta": None},
    },
    "vessels": [{"name": "COSCO SHIPPING GEMINI", "imo": 9783538}],
    "containers": [{
        "number": "SZLU5121564",
        "events": [
            {"status": "CLL", "eventCode": "LOAD", "date": "2026-09-23T19:08:00Z", "isActual": True,
             "vessel": {"name": "COSCO SHIPPING GEMINI", "imo": 9783538}, "voyage": "0FAO1W1MA", "location": {"locode": "CNQDG"}},
            {"status": "VAD", "eventCode": "ARRI", "date": "2026-11-03T07:00:00Z", "isActual": False,
             "vessel": {"name": "COSCO SHIPPING GEMINI", "imo": 9783538}, "voyage": "0FAO2E1MA",
             "location": {"locode": "NLRTM"}, "facility": {"name": "ECT Euromax"}},
        ],
    }],
}


@override_settings(SAFECUBE_API_KEY="sk-test", SAFECUBE_BASE_URL="https://api.example.com/ct/v2", SAFECUBE_API_KEY_HEADER="API_KEY")
class SafecubeTests(TestCase):
    def setUp(self):
        customer = Customer.objects.create(name="EUROFOODLINK")
        line = ShippingLine.objects.create(name="CMA CGM", scac="CMDU", tracking_provider="safecube")
        self.shipment = SeaShipment.objects.create(customer=customer, shipping_line=line, container_number="SZLU5121564",
                                                   bl_number="QGD3466869", vessel_name="COSCO GEMINI")

    def test_request_and_parse(self):
        resp = mock.Mock(status_code=200, json=lambda: SAFECUBE_SAMPLE, text="")
        with mock.patch("shipments.tracking.safecube.requests.get", return_value=resp) as get:
            update = refresh_shipment(self.shipment)
        self.assertTrue(update.success, update.message)
        params = get.call_args.kwargs["params"]
        self.assertEqual((params["shipmentNumber"], params["shipmentType"], params["sealine"]), ("QGD3466869", "BL", "CMDU"))
        self.assertEqual(get.call_args.args[0], "https://api.example.com/ct/v2/shipment")
        self.assertEqual(get.call_args.kwargs["headers"]["API_KEY"], "sk-test")
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.vessel_name, "COSCO SHIPPING GEMINI")
        self.assertFalse(self.shipment.vessel_changed)  # "COSCO GEMINI" is hetzelfde schip
        self.assertEqual(self.shipment.voyage, "0FAO2E1MA")
        self.assertEqual(self.shipment.vessel_imo, "9783538")
        self.assertEqual(self.shipment.eta.isoformat(), "2026-11-03T07:00:00+00:00")
        self.assertIsNone(self.shipment.ata)
        self.assertEqual(self.shipment.port_of_loading, "CNQDG")  # de UN/LOCODE die Safecube meegeeft
        self.assertEqual(self.shipment.terminal, "ECT Euromax Terminal")  # "ECT Euromax" -> volledige naam

    def test_no_info_yet_is_pending_and_timeout(self):
        resp = mock.Mock(status_code=200, json=lambda: {"message": "SEALINE_HASNT_PROVIDE_INFO"}, text="")
        with mock.patch("shipments.tracking.safecube.requests.get", return_value=resp):
            update = refresh_shipment(self.shipment)
        self.assertTrue(update.success)
        self.assertIn("SEALINE_HASNT_PROVIDE_INFO", update.message)
        with mock.patch("shipments.tracking.safecube.requests.get", return_value=mock.Mock(status_code=504, json=dict, text="")):
            update = refresh_shipment(self.shipment)
        self.assertTrue(update.success)

    def test_bad_key(self):
        resp = mock.Mock(status_code=401, json=lambda: {"message": "Invalid API key"}, text="")
        with mock.patch("shipments.tracking.safecube.requests.get", return_value=resp):
            update = refresh_shipment(self.shipment)
        self.assertFalse(update.success)
        self.assertIn("Invalid API key", update.message)

    def test_refresh_all_respects_six_hours(self):
        from .tracking.service import refresh_all

        self.shipment.tracking_last_checked = timezone.now() - timedelta(hours=2)
        self.shipment.save()
        with mock.patch("shipments.tracking.safecube.requests.get") as get:
            refresh_all()
        get.assert_not_called()


class PasteAndQuickUpdateTests(TestCase):
    def setUp(self):
        from pathlib import Path

        self.text = (Path(__file__).parent / "testdata" / "cma_cgm_tracking.txt").read_text()
        self.client.force_login(User.objects.create_superuser("admin", "a@example.com", "pw"))
        customer = Customer.objects.create(name="EUROFOODLINK")
        line = ShippingLine.objects.create(name="CMA CGM", scac="CMDU", tracking_provider="none",
                                           tracking_url_template="https://www.cma-cgm.com/ebusiness/tracking/search")
        self.shipment = SeaShipment.objects.create(customer=customer, shipping_line=line, container_number="SZLU5121564",
                                                   bl_number="QGD3466869", vessel_name="COSCO GEMINI")

    def test_parse_cma_cgm_page(self):
        from .paste import parse_tracking_text

        r = parse_tracking_text(self.text)
        local = timezone.localtime(r.eta)
        self.assertEqual((local.day, local.month, local.hour), (3, 11, 8))
        self.assertEqual((r.vessel_name, r.voyage), ("COSCO SHIPPING GEMINI", "0FAO2E1MA"))
        self.assertEqual(r.port_of_loading, "QINGDAO (CN)")
        self.assertEqual(r.port_of_discharge, "ROTTERDAM (NL)")
        self.assertEqual(r.terminal, "ECT EUROMAX ROTTERDAM")
        self.assertIsNone(r.ata)
        self.assertEqual(timezone.localtime(r.departed_at).day, 24)
        self.assertIsNone(parse_tracking_text("geen bruikbare tekst"))

    def test_paste_view_updates_shipment(self):
        r = self.client.post(f"/zendingen/zeevracht/{self.shipment.pk}/plakken/", {"text": self.text})
        self.assertEqual(r.status_code, 302)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.voyage, "0FAO2E1MA")
        self.assertEqual(self.shipment.port_of_loading, "CNTAO")
        self.assertEqual(self.shipment.terminal, "ECT Euromax Terminal")
        self.assertFalse(self.shipment.vessel_changed)
        self.assertIsNotNone(self.shipment.departed_at)
        self.assertEqual(self.shipment.tracking_updates.get().provider, "geplakt")
        self.assertIsNotNone(self.shipment.voyage_progress)

    def test_paste_delivered_container(self):
        """CMA CGM-pagina van een afgeronde reis: aankomst, lossen, gate out en havens worden overgenomen."""
        from pathlib import Path

        text = (Path(__file__).parent / "testdata" / "cma_cgm_tracking_delivered.txt").read_text()
        self.shipment.vessel_name, self.shipment.port_of_loading = "MAERSK LONDRINA", "PARANAGUA"
        self.shipment.save()
        self.assertEqual(self.shipment.port_of_loading, "BRPNG")
        with mock.patch("django.utils.timezone.now", return_value=timezone.make_aware(datetime(2026, 10, 6, 15, 0))):
            self.client.post(f"/zendingen/zeevracht/{self.shipment.pk}/plakken/", {"text": text})
        self.shipment.refresh_from_db()
        local = lambda d: timezone.localtime(d).strftime("%d-%m %H:%M")  # noqa: E731
        self.assertEqual(local(self.shipment.ata), "03-10 13:00")
        self.assertEqual(local(self.shipment.discharged_at), "03-10 17:26")
        self.assertEqual(local(self.shipment.departed_at), "11-09 22:33")
        self.assertEqual((self.shipment.voyage, self.shipment.terminal), ("0EWORS1MA", "Hutchison Ports Delta II"))
        self.assertEqual((self.shipment.port_of_loading, self.shipment.port_of_discharge), ("BRPNG", "NLRTM"))
        self.assertEqual(self.shipment.status, "uitgeleverd")
        self.assertFalse(self.shipment.vessel_changed)
        page = self.client.get(f"/zendingen/zeevracht/{self.shipment.pk}/")
        self.assertContains(page, "Paranaguá, Brazilië (BRPNG)")
        self.assertContains(page, "Rotterdam, Nederland (NLRTM)")

    def test_quick_update_and_detail_page(self):
        url = f"/zendingen/zeevracht/{self.shipment.pk}/"
        self.client.post(url + "snel/", {"inspection_status": "aangemeld"})
        self.client.post(url + "snel/", {"customs_cleared": "1"})
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.inspection_status, "aangemeld")
        self.assertTrue(self.shipment.customs_cleared)
        page = self.client.get(url)
        self.assertContains(page, "Bekijk bij rederij")
        self.assertContains(page, "Plak tracking")

    def test_list_views_and_csv(self):
        self.shipment.eta = timezone.now() + timedelta(days=2)
        self.shipment.save()
        page = self.client.get("/zendingen/zeevracht/?weergave=week")
        self.assertContains(page, "SZLU")
        self.assertEqual([v["count"] for v in page.context["views"] if v["key"] == "ched"], [1])
        csv = self.client.get("/zendingen/zeevracht/?weergave=alle&export=csv")
        self.assertIn("SZLU5121564", csv.content.decode())
        self.assertNotContains(self.client.get("/zendingen/zeevracht/?weergave=gewisseld"), "SZLU5121564")


class VesselImoTests(TestCase):
    def test_imo_cleared_on_vessel_change_without_imo(self):
        from .tracking.service import apply_result

        customer = Customer.objects.create(name="K")
        s = SeaShipment.objects.create(customer=customer, container_number="CSQU3054383", vessel_name="MAERSK HIDALGO", vessel_imo="9786786")
        apply_result(s, TrackingResult(provider="geplakt", vessel_name="COSCO SHIPPING GEMINI"))
        s.refresh_from_db()
        self.assertTrue(s.vessel_changed)
        self.assertEqual(s.vessel_imo, "")
