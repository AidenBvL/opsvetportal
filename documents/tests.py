import shutil
import tempfile
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from core.models import Customer, InspectionPoint, ShippingLine
from shipments.models import SeaShipment

from .models import Document
from .parser import ExtractionError, extract_fields, extract_text, find_containers, parse_date

SAMPLE_BL = """
MAERSK                                   BILL OF LADING
B/L No.: MAEU254123987            Booking No: 254123987
Shipper: Pesquera Ejemplo S.A., Guayaquil
Consignee: Voorbeeld Seafood Import BV, Rotterdam
Your Ref: PO-88812
Ocean Vessel: MAERSK HIDALGO  Voy. 642W
Port of Loading: Guayaquil, Ecuador
Port of Discharge: Rotterdam, Netherlands
ETA: 14-10-2026
Container No.     Seal No.      Type
CSQU 305438 3     SEAL: ML123456   40' RH
MSKU9070323       SEAL: ML123457   40RH
MSKU9070324 (ongeldig controlecijfer)
Description of goods: FROZEN SHRIMPS (VANNAMEI) 1.800 CARTONS
Temperature set point: -18.0 C
Gross weight: 24.580,00 KGS
CHED reference CHEDP.NL.2026.0012345 - inspection at GCP Maasvlakte
"""


class ParserTests(TestCase):
    def test_extract_fields(self):
        data = extract_fields(SAMPLE_BL)
        numbers = [c["container_number"] for c in data["containers"]]
        self.assertEqual(numbers, ["CSQU3054383", "MSKU9070323"])
        self.assertEqual(data["containers"][0]["container_type"], "40RH")
        self.assertEqual(data["containers"][0]["seal_number"], "ML123456")
        self.assertEqual(data["bl_number"], "MAEU254123987")
        self.assertEqual(data["booking_number"], "254123987")
        self.assertEqual(data["vessel_name"], "MAERSK HIDALGO")
        self.assertEqual(data["voyage"], "642W")
        self.assertEqual(data["eta"], "2026-10-14")
        self.assertTrue(data["port_of_loading"].startswith("Guayaquil"))
        self.assertTrue(data["port_of_discharge"].startswith("Rotterdam"))
        self.assertEqual(data["ched_number"], "CHEDP.NL.2026.0012345")
        self.assertEqual(data["customer_reference"], "PO-88812")
        self.assertEqual(data["temperature_setpoint"], "-18.0")
        self.assertIn("FROZEN SHRIMPS", data["goods_description"])

    def test_parse_date_formats(self):
        self.assertEqual(str(parse_date("14/10/2026")), "2026-10-14")
        self.assertEqual(str(parse_date("2026-10-14")), "2026-10-14")
        self.assertEqual(str(parse_date("14 OCT 2026")), "2026-10-14")
        self.assertEqual(str(parse_date("3 mrt 2026")), "2026-03-03")
        self.assertIsNone(parse_date("geen datum"))

    def test_find_containers_dedupes(self):
        self.assertEqual(len(find_containers("CSQU3054383 en nogmaals CSQU 3054383")), 1)

    def test_unsupported_extension(self):
        with self.assertRaises(ExtractionError):
            extract_text("/tmp/bestand.docx")

    def test_missing_tesseract_gives_clear_error(self):
        import pytesseract

        with mock.patch.object(pytesseract, "image_to_string", side_effect=pytesseract.TesseractNotFoundError()):
            from PIL import Image

            from .parser import ocr_image

            with self.assertRaises(ExtractionError) as ctx:
                ocr_image(Image.new("RGB", (10, 10)))
            self.assertIn("Tesseract", str(ctx.exception))


class UploadFlowTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.user = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name="Voorbeeld Seafood Import BV")
        self.line = ShippingLine.objects.create(name="Maersk", scac="MAEU")
        self.point = InspectionPoint.objects.create(name="GCP Maasvlakte")

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media, ignore_errors=True)

    def test_upload_review_and_create(self):
        upload = SimpleUploadedFile("bl.txt", SAMPLE_BL.encode(), content_type="text/plain")
        r = self.client.post("/documenten/uploaden/", {"file": upload, "doc_type": "bl", "customer": self.customer.pk})
        document = Document.objects.get()
        self.assertRedirects(r, f"/documenten/{document.pk}/verwerken/")
        self.assertEqual(document.extracted_data["shipping_line_id"], self.line.pk)
        self.assertEqual(document.extracted_data["inspection_point_id"], self.point.pk)

        page = self.client.get(f"/documenten/{document.pk}/verwerken/")
        self.assertContains(page, "MAERSK HIDALGO")
        form = page.context["form"]
        data = {k: v for k, v in form.initial.items() if v is not None}
        data["inspection_required"] = "on"
        data["eta"] = form.initial["eta"].strftime("%Y-%m-%dT%H:%M")
        r = self.client.post(f"/documenten/{document.pk}/verwerken/", data)
        self.assertEqual(r.status_code, 302, getattr(r, "context", {}) and r.context["form"].errors)
        self.assertEqual(SeaShipment.objects.count(), 2)
        s = SeaShipment.objects.get(container_number="CSQU3054383")
        self.assertEqual(s.vessel_name, "MAERSK HIDALGO")
        self.assertEqual(s.shipping_line, self.line)
        self.assertEqual(s.ched_number, "CHEDP.NL.2026.0012345")
        self.assertEqual(s.seal_number, "ML123456")
        self.assertEqual(list(document.sea_shipments.order_by("pk")), list(SeaShipment.objects.order_by("pk")))

        # Tweede keer verwerken vult aan in plaats van dubbel aanmaken.
        self.client.post(f"/documenten/{document.pk}/verwerken/", data)
        self.assertEqual(SeaShipment.objects.count(), 2)

    def test_rejects_unknown_file_type(self):
        upload = SimpleUploadedFile("macro.exe", b"MZ")
        r = self.client.post("/documenten/uploaden/", {"file": upload, "doc_type": "other"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Document.objects.exists())
