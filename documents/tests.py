import shutil
from decimal import Decimal
import tempfile
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from core.models import Customer, InspectionPoint, ShippingLine
from shipments.models import SeaShipment

from .layout import extract_layout_fields
from .models import Document
from .parser import (
    ExtractionError, extract_fields, extract_text, find_containers, match_master_data, merge_layout, parse_date, parse_number,
)

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
        # Twee containers en alleen een totaalgewicht: niet op elke container zetten.
        self.assertIsNone(s.gross_weight_kg)
        self.assertEqual(list(document.sea_shipments.order_by("pk")), list(SeaShipment.objects.order_by("pk")))

        # Tweede keer verwerken vult aan in plaats van dubbel aanmaken.
        self.client.post(f"/documenten/{document.pk}/verwerken/", data)
        self.assertEqual(SeaShipment.objects.count(), 2)

    def test_rejects_unknown_file_type(self):
        upload = SimpleUploadedFile("macro.exe", b"MZ")
        r = self.client.post("/documenten/uploaden/", {"file": upload, "doc_type": "other"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Document.objects.exists())


def _words(*rows, height=7):
    """Bouw pdfplumber-achtige woorden: rows = (top, [(x0, tekst), ...]) of (top, [...], hoogte)."""
    words = []
    for row in rows:
        top, items = row[0], row[1]
        h = row[2] if len(row) > 2 else height
        for x0, text in items:
            words.append({"text": text, "x0": x0, "x1": x0 + (4.9 if h < 10 else 6.6) * len(text), "top": top, "bottom": top + h})
    return words


# Uitsnede van een CMA CGM sea waybill: labels boven, waarden eronder (en soms iets naar links).
WAYBILL_WORDS = _words(
    (12, [(511, "VOYAGE"), (543, "NUMBER")]),
    (15, [(5, "SHIPPER")]),
    (25, [(3, "VIBRA"), (29, "AGROINDUSTRIAL"), (102, "S/A"), (510, "0EWOAN1MA")]),
    (42, [(504, "WAYBILL"), (536, "NUMBER")]),
    (52, [(331, "NON"), (365, "NEGOTIABLE")]),
    (57, [(518, "SSZ1840212")]),
    (85, [(6, "CONSIGNEE"), (288, "EXPORT"), (319, "REFERENCES")]),
    (97, [(3, "J.A."), (18, "TER"), (37, "MATEN")]),
    (106, [(3, "DE"), (16, "KOOIHOEK"), (61, "7")]),
    (259, [(55, "VESSEL"), (179, "PORT"), (200, "OF"), (212, "LOADING"), (325, "PORT"), (346, "OF"), (358, "DISCHARGE"),
           (466, "FINAL"), (488, "PLACE"), (513, "OF"), (524, "DELIVERY*")]),
    (268, [(2, "MAERSK"), (39, "LONDRINA"), (133, "PARANAGUA"), (283, "ROTTERDAM")]),
    (600, [(3, "carry"), (30, "on"), (45, "any"), (65, "Vessel")]),
    (609, [(3, "something"), (60, "else")]),
)

WAYBILL_TEXT = """VOYAGE NUMBER
SHIPPER
CONSIGNEE EXPORT REFERENCES
J.A. TER MATEN
VESSEL PORT OF LOADING PORT OF DISCHARGE FINAL PLACE OF DELIVERY*
MAERSK LONDRINA PARANAGUA ROTTERDAM
SEGU9074220 1 x 40RH 21 CARTONS 22909.950 4650 25.200
SEAL K1108089
Vibra Ingredients NCM: 0511.99.99 - 22050 (KG) -
FROZEN CHICKEN GIBLETS - LIVER -
Cargo is stowed in a refrigerated container set
at the shipper's requested carrying temperature
of -22 degrees Celsius
Shipped on Board MAERSK LONDRINA 11-SEP-2026 CMA CGM do Brasil
SIGNED FOR THE CARRIER CMA CGM S.A.
"""


# Uitsnede van een Hapag-Lloyd sea waybill: kleine labels met ':' en gemengde hoofdletters, waarden groter eronder.
HAPAG_WORDS = _words(
    (31, [(40, "Shipper:")]),
    (40, [(43, "AGRICOLA"), (102, "ARIZTIA"), (155, "LTDA.")], 12),
    (80, [(302, "Carrier’s"), (330, "Reference:"), (374, "SWB-No.:"), (510, "Page:")]),
    (89, [(309, "10276183"), (381, "HLCUSCL260910263"), (518, "2")], 12),
    (115, [(40, "Consignee:")]),
    (124, [(43, "J.A."), (79, "TER"), (108, "MATEN,")], 12),
    (283, [(40, "Vessel(s):"), (242, "Voyage-No.:")]),
    (292, [(43, "COSCO"), (86, "SHIPPING"), (150, "SEINE"), (259, "6232N")], 12),
    (295, [(302, "Place"), (320, "of"), (328, "Delivery:")]),
    (319, [(40, "Port"), (55, "of"), (63, "Loading:")]),
    (328, [(43, "SAN"), (72, "ANTONIO,"), (132, "CHILE")], 12),
    (343, [(40, "Port"), (55, "of"), (63, "Discharge:")]),
    (352, [(43, "ROTTERDAM,"), (115, "NETHERLANDS")], 12),
    (700, [(40, "VESSEL"), (75, "NAME:"), (110, "OTHER"), (150, "SHIP"), (190, "VOYAGE:"), (240, "999X")]),
)


class LayoutTests(TestCase):
    def test_label_meaning_not_per_carrier(self):
        from .layout import classify

        cases = {
            "Port of Loading:": "port_of_loading", "PORT OF DISCHARGE": "port_of_discharge", "POD": "port_of_discharge",
            "Vessel(s):": "vessel_name", "OCEAN VESSEL": "vessel_name", "Vessel / Voyage": "vessel_voyage",
            "Voyage-No.:": "voyage", "VOYAGE NUMBER": "voyage", "SWB-No.:": "bl_number", "B/L No.": "bl_number",
            "WAYBILL NUMBER": "bl_number", "NUMBER OF ORIGINAL WAYBILLS": None, "Booking No:": "booking_number",
            "Carrier’s Reference:": "booking_number", "Consignee’s Reference:": "customer_reference",
            "Consignee:": "consignee", "Notify Address (Carrier not responsible for failure to notify):": "notify",
            "Place of Delivery:": None, "AS STATED BY SHIPPER": None,
        }
        for label, field in cases.items():
            self.assertEqual(classify(label), field, label)

    def test_hapag_style_labels(self):
        fields = extract_layout_fields([HAPAG_WORDS])
        self.assertEqual(fields["bl_number"], "HLCUSCL260910263")
        self.assertEqual(fields["booking_number"], "10276183")
        self.assertEqual(fields["vessel_name"], "COSCO SHIPPING SEINE")
        self.assertEqual(fields["voyage"], "6232N")
        self.assertEqual(fields["port_of_loading"], "SAN ANTONIO, CHILE")
        self.assertEqual(fields["port_of_discharge"], "ROTTERDAM, NETHERLANDS")
        self.assertEqual(fields["consignee"], "J.A. TER MATEN")
        self.assertTrue(fields["shipper"].startswith("AGRICOLA ARIZTIA"))

    def test_value_right_of_label(self):
        fields = extract_layout_fields([_words((10, [(40, "VESSEL"), (75, "NAME:"), (105, "COSCO"), (135, "SEINE"),
                                                    (165, "VOYAGE:"), (205, "6232N")]))])
        self.assertEqual((fields["vessel_name"], fields["voyage"]), ("COSCO SEINE", "6232N"))

    def test_values_below_labels(self):
        fields = extract_layout_fields([WAYBILL_WORDS])
        self.assertEqual(fields["voyage"], "0EWOAN1MA")
        self.assertEqual(fields["bl_number"], "SSZ1840212")
        self.assertEqual(fields["vessel_name"], "MAERSK LONDRINA")
        self.assertEqual(fields["port_of_loading"], "PARANAGUA")
        self.assertEqual(fields["port_of_discharge"], "ROTTERDAM")
        self.assertEqual(fields["consignee"].splitlines()[0], "J.A. TER MATEN")
        self.assertTrue(fields["shipper"].startswith("VIBRA AGROINDUSTRIAL"))

    def test_waybill_text_fields(self):
        data = merge_layout(extract_fields(WAYBILL_TEXT), extract_layout_fields([WAYBILL_WORDS]))
        self.assertEqual(data["temperature_setpoint"], "-22")
        self.assertEqual(data["goods_description"], "FROZEN CHICKEN GIBLETS - LIVER")
        self.assertEqual(data["departed_at"], "2026-09-11")
        self.assertEqual(data["port_of_discharge"], "NLRTM")
        self.assertEqual(data["port_of_loading"], "BRPNG")
        self.assertEqual(data["containers"][0]["seal_number"], "K1108089")
        self.assertEqual((data["packages"], data["package_type"], data["gross_weight_kg"]), ("21", "CARTONS", "22909.950"))

    def test_hapag_text_fields(self):
        text = """HLBU 9848255 1600 BLOCKS 24400,000
SEALS : 1 X 40 REEFER CONTAINER KGM
HLK1844222
Container Nos., Seal Nos.; Marks and Nos. Number and Kind of Packages, Description of Goods Gross Weight: Measurement:
Cont/Seals/Marks Packages/Description of Goods Weight Measure
24000,00 NET WEIGHT OF
FROZEN CHICKEN LIVERS
TEMPERATURE TO BE SET AT -20,0 C
SHIPPED ON BOARD, DATE : 18.SEP.2026
"""
        data = extract_fields(text)
        container = data["containers"][0]
        self.assertEqual((container["container_number"], container["seal_number"]), ("HLBU9848255", "HLK1844222"))
        self.assertEqual((data["packages"], data["package_type"], data["gross_weight_kg"]), ("1600", "BLOCKS", "24400.000"))
        self.assertEqual(data["goods_description"], "FROZEN CHICKEN LIVERS")
        self.assertEqual(data["temperature_setpoint"], "-20.0")
        self.assertEqual(data["departed_at"], "2026-09-18")
        self.assertEqual(merge_layout(data, {"port_of_loading": "SAN ANTONIO, CHILE"})["port_of_loading"], "CLSAI")

    def test_parse_number(self):
        self.assertEqual(parse_number("22909.950"), "22909.950")
        self.assertEqual(parse_number("24.580,00"), "24580.00")
        self.assertEqual(parse_number("1,234,567.8"), "1234567.8")
        self.assertEqual(parse_number("12,5"), "12.5")
        self.assertEqual(parse_number("geen"), "")

    def test_customer_and_carrier_matching(self):
        maersk = ShippingLine.objects.create(name="Maersk", scac="MAEU")
        cma = ShippingLine.objects.create(name="CMA CGM", scac="CMDU")
        customer = Customer.objects.create(name="J.A. Ter Maten")
        Customer.objects.create(name="Eurofoodlink B.V.")
        data = match_master_data(WAYBILL_TEXT, merge_layout(extract_fields(WAYBILL_TEXT), extract_layout_fields([WAYBILL_WORDS])))
        self.assertEqual(data["customer_id"], customer.pk)
        # "MAERSK" staat alleen in de scheepsnaam; de vervoerder is CMA CGM.
        self.assertEqual(data["shipping_line_id"], cma.pk)
        self.assertNotEqual(data["shipping_line_id"], maersk.pk)


class ShipmentDocumentTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.user = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name="Voorbeeld Seafood Import BV")
        self.shipment = SeaShipment.objects.create(customer=self.customer, container_number="CSQU3054383")

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media, ignore_errors=True)

    def upload(self, *files, doc_type="other"):
        return self.client.post(f"/documenten/zending/zee/{self.shipment.pk}/uploaden/", {"files": list(files), "doc_type": doc_type})

    def test_upload_link_open_and_unlink(self):
        r = self.upload(SimpleUploadedFile("factuur.pdf", b"%PDF-1.4 kapot", content_type="application/pdf"),
                        SimpleUploadedFile("instructies.docx", b"PK..", content_type="application/octet-stream"))
        self.assertRedirects(r, f"/zendingen/zeevracht/{self.shipment.pk}/#tab-docs", fetch_redirect_response=False)
        self.assertEqual(self.shipment.documents.count(), 2)
        pdf = Document.objects.get(original_name="factuur.pdf")
        self.assertEqual(pdf.customer, self.customer)
        self.assertEqual(bytes(pdf.content), b"%PDF-1.4 kapot")

        page = self.client.get(f"/zendingen/zeevracht/{self.shipment.pk}/")
        self.assertContains(page, "factuur.pdf")
        self.assertContains(page, f"/documenten/{pdf.pk}/bestand/")

        r = self.client.get(f"/documenten/{pdf.pk}/bestand/")
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r["Content-Disposition"].startswith("inline"))
        self.assertEqual(r.content, b"%PDF-1.4 kapot")
        docx = Document.objects.get(original_name="instructies.docx")
        self.assertTrue(self.client.get(f"/documenten/{docx.pk}/bestand/")["Content-Disposition"].startswith("attachment"))
        self.assertEqual(docx.status, "gekoppeld")

        self.client.post(f"/documenten/{pdf.pk}/ontkoppelen/zee/{self.shipment.pk}/")
        self.assertEqual(self.shipment.documents.count(), 1)
        self.assertTrue(Document.objects.filter(pk=pdf.pk).exists())

    def test_file_survives_missing_disk(self):
        self.upload(SimpleUploadedFile("bl.txt", SAMPLE_BL.encode(), content_type="text/plain"), doc_type="bl")
        document = Document.objects.get()
        self.assertEqual(document.status, "gekoppeld")
        self.assertIn("CSQU3054383", [c["container_number"] for c in document.extracted_data["containers"]])
        import os

        os.remove(document.file.path)  # bijv. na een nieuwe deploy op Render
        self.assertEqual(self.client.get(f"/documenten/{document.pk}/bestand/").content, SAMPLE_BL.encode())
        self.client.post(f"/documenten/{document.pk}/opnieuw/")
        document.refresh_from_db()
        self.assertEqual(document.status, "verwerkt")

    def test_review_takes_weight_and_packages(self):
        self.shipment.container_number = "SEGU9074220"
        self.shipment.save()
        self.upload(SimpleUploadedFile("swb.txt", WAYBILL_TEXT.encode(), content_type="text/plain"), doc_type="bl")
        document = Document.objects.get()
        form = self.client.get(f"/documenten/{document.pk}/verwerken/").context["form"]
        data = {k: v for k, v in form.initial.items() if v not in (None, "")}
        data["customer"] = self.customer.pk
        self.client.post(f"/documenten/{document.pk}/verwerken/", data)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.gross_weight_kg, Decimal("22909.950"))
        self.assertEqual((self.shipment.packages, self.shipment.package_type), (21, "CARTONS"))
        self.assertEqual(self.shipment.temperature_setpoint, Decimal("-22.0"))

    def test_rejects_unknown_type_and_requires_login(self):
        self.upload(SimpleUploadedFile("virus.exe", b"MZ"))
        self.assertFalse(Document.objects.exists())
        self.upload(SimpleUploadedFile("ok.txt", b"hallo"))
        document = Document.objects.get()
        self.client.logout()
        self.assertNotEqual(self.client.get(f"/documenten/{document.pk}/bestand/").status_code, 200)
