"""Tekstherkenning (PDF-tekstlaag of Tesseract OCR) en het uitlezen van zendinggegevens.

`extract_text` probeert eerst de tekstlaag van een PDF (snel en foutloos). Is die er
niet (gescand document) of is het een afbeelding, dan wordt Tesseract gebruikt als
het geïnstalleerd is. `extract_fields` haalt daarna de relevante velden uit de tekst.
"""

import re
from datetime import datetime
from pathlib import Path

from django.conf import settings

from shipments.validators import is_valid_container_number

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
TEXT_EXTENSIONS = {".pdf", ".txt", ".csv", ".edi"} | IMAGE_EXTENSIONS
MIN_TEXT_LENGTH = 40


class ExtractionError(Exception):
    pass


def _tesseract():
    try:
        import pytesseract
    except ImportError as exc:  # pragma: no cover - afhankelijk van installatie
        raise ExtractionError("pytesseract is niet geïnstalleerd.") from exc
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    return pytesseract


def ocr_image(image):
    pytesseract = _tesseract()
    try:
        return pytesseract.image_to_string(image, lang=settings.TESSERACT_LANG)
    except pytesseract.TesseractNotFoundError as exc:
        raise ExtractionError(
            "Tesseract is niet gevonden. Installeer het (apt install tesseract-ocr tesseract-ocr-nld) "
            "of zet TESSERACT_CMD."
        ) from exc
    except pytesseract.TesseractError:
        # Taalpakket ontbreekt: val terug op Engels.
        return pytesseract.image_to_string(image, lang="eng")


def extract_text(path):
    """Geeft (tekst, methode) terug."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext in {".txt", ".csv", ".edi"}:
        return path.read_text(errors="ignore"), "tekst"
    if ext == ".pdf":
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            if len(text.strip()) >= MIN_TEXT_LENGTH:
                return text, "pdf-tekst"
            pages = [ocr_image(page.to_image(resolution=300).original) for page in pdf.pages]
            return "\n".join(pages), "ocr"
    if ext in IMAGE_EXTENSIONS:
        from PIL import Image

        with Image.open(path) as image:
            return ocr_image(image), "ocr"
    raise ExtractionError(f"Bestandstype {ext} wordt niet ondersteund.")


# ---------------------------------------------------------------------------
# Velden uitlezen
# ---------------------------------------------------------------------------

CONTAINER_PATTERN = re.compile(r"\b([A-Z]{3}[UJZ])[\s\-]?(\d{6})[\s\-]?(\d)\b")
CONTAINER_TYPE_PATTERN = re.compile(r"\b(20|40|45)\s*'?\s*(DV|DC|GP|HC|HQ|RF|RH|REEFER|HR)\b", re.I)
DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"), "dmy"),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[\s\-]([A-Za-z]{3})[A-Za-z]*[\s\-,]+(\d{4})\b"), "dMy"),
]
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "mrt": 3, "apr": 4, "may": 5, "mei": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "okt": 10, "nov": 11, "dec": 12,
}  # fmt: skip
TEMPERATURE_PATTERN = (
    r"(?:TEMP(?:ERATURE|ERATUUR)?|SET\s*POINT)[^\d\-+]{0,40}?([\-+]?\d{1,2}(?:[.,]\d)?)\s*"
    r"(?:°\s*C\b|º\s*C\b|DEG(?:REES?|R)?\.?\s*(?:C(?:ELSIUS)?\b)?|C\b)"
)
GOODS_KEYWORDS = re.compile(r"\b(?:FROZEN|CHILLED|FRESH|DRIED|SALTED|SMOKED|DIEPGEVROREN|BEVROREN|GEKOELD|VERS)\b", re.I)


def _first(pattern, text, flags=re.I | re.M, group=1):
    match = re.search(pattern, text, flags)
    return match.group(group).strip(" :\t").rstrip(".") if match else ""


def parse_date(value):
    for pattern, order in DATE_PATTERNS:
        match = pattern.search(value or "")
        if not match:
            continue
        a, b, c = match.groups()
        try:
            if order == "dmy":
                return datetime(int(c), int(b), int(a)).date()
            if order == "ymd":
                return datetime(int(a), int(b), int(c)).date()
            month = MONTHS.get(b[:3].lower())
            if month:
                return datetime(int(c), month, int(a)).date()
        except ValueError:
            continue
    return None


def _container_type(fragment):
    match = CONTAINER_TYPE_PATTERN.search(fragment)
    if not match:
        return ""
    size, kind = match.group(1), match.group(2).upper()
    if kind in {"RF", "RH", "REEFER", "HR"}:
        return "20RF" if size == "20" else "40RH"
    if kind in {"HC", "HQ"}:
        return "40HC"
    return "20DV" if size == "20" else "40DV"


def find_containers(text):
    containers = []
    seen = set()
    upper = (text or "").upper()
    for match in CONTAINER_PATTERN.finditer(upper):
        number = "".join(match.groups())
        if number in seen or not is_valid_container_number(number):
            continue
        seen.add(number)
        fragment = upper[match.end() : match.end() + 80]
        seal = _first(r"(?:SEAL|ZEGEL)\s*(?:NO\.?|NR\.?|#)?\s*[:\-]?\s*([A-Z0-9]{5,15})", fragment)
        containers.append({"container_number": number, "container_type": _container_type(fragment), "seal_number": seal})
    return containers


def extract_fields(text):
    text = text or ""
    vessel_line = _first(r"(?:OCEAN\s+)?VESSEL(?:\s+NAME)?(?:\s*/\s*VOY(?:AGE)?)?\s*[:\-]\s*(.+)$", text)
    vessel, voyage = vessel_line, ""
    split = re.match(r"(.+?)\s+(?:V\.?|VOY(?:AGE)?\.?(?:\s*NO\.?)?)\s*([A-Z0-9]{3,10})\s*$", vessel_line, re.I)
    if split:
        vessel, voyage = split.group(1), split.group(2)
    voyage = voyage or _first(r"\bVOY(?:AGE)?\.?\s*(?:NO\.?|NUMBER|NR\.?)?\s*[:\-]\s*([A-Z0-9]{3,12})\b", text)

    eta_raw = _first(r"\bETA\b[^\n\d]{0,20}([^\n]{6,30})", text)
    flat = re.sub(r"\s+", " ", text)
    temperature = _first(TEMPERATURE_PATTERN, flat)
    weight = _first(r"GROSS\s*WEIGHT[^\n\d]{0,25}([\d.,]+)\s*KGS?", text) or _first(r"BRUTO\s*GEWICHT[^\n\d]{0,25}([\d.,]+)", text)

    data = {
        "containers": find_containers(text),
        "bl_number": _first(
            r"(?:B/?L|BILL\s+OF\s+LADING|(?:SEA\s*)?WAYBILL)\s*(?:NO\.?|NUMBER|NR\.?|#)?\s*[:\-]?\s*((?=[A-Z0-9]*\d)[A-Z]{2,4}[A-Z0-9]{6,16})\b", text
        ),
        "booking_number": _first(r"BOOKING\s*(?:NO\.?|NUMBER|NR\.?|REF\.?)?\s*[:\-]?\s*([A-Z0-9]{6,20})\b", text),
        "vessel_name": vessel.strip().upper()[:150],
        "voyage": voyage.upper(),
        "port_of_loading": _not_a_label(_first(r"PORT\s+OF\s+LOADING\s*[:\-]?\s*([^\n]{2,60})", text)),
        "port_of_discharge": _not_a_label(_first(r"PORT\s+OF\s+DISCHARGE\s*[:\-]?\s*([^\n]{2,60})", text)),
        "eta": (parse_date(eta_raw).isoformat() if parse_date(eta_raw) else ""),
        "ched_number": _first(r"\b(CHED[PDA]?(?:PP)?\.[A-Z]{2}\.\d{4}\.\d{5,8})\b", text),
        "customer_reference": _first(r"(?:YOUR|CUSTOMER|KLANT)\s*REF(?:ERENCE|ERENTIE)?\.?\s*[:\-]\s*([A-Z0-9\-/]{3,40})", text),
        "temperature_setpoint": temperature.replace(",", "."),
        "gross_weight_kg": weight,
        "goods_description": _first(r"(?:DESCRIPTION\s+OF\s+GOODS|GOEDERENOMSCHRIJVING|COMMODITY)\s*[:\-]?\s*([^\n]{3,120})", text)
        or _goods_line(text),
        "departed_at": "",
    }
    shipped = _first(r"SHIPPED\s+ON\s+BOARD[^\n]{0,60}?(\d{1,2}[\s\-/.][A-Z0-9]{2,9}[\s\-/.,]+\d{4})", text)
    if parse_date(shipped):
        data["departed_at"] = parse_date(shipped).isoformat()
    return data


def _not_a_label(value):
    """Een kolomkop als "PORT OF DISCHARGE FINAL PLACE OF DELIVERY" is geen waarde."""
    return "" if re.search(r"\b(?:PORT|PLACE)\s+OF\b|\bVESSEL\b|\bDELIVERY\b", value, re.I) else value


# Veelvoorkomende loshavens als UN/LOCODE (zo verwacht de tracking ze).
PORT_LOCODES = {
    "ROTTERDAM": "NLRTM", "AMSTERDAM": "NLAMS", "VLISSINGEN": "NLVLI", "FLUSHING": "NLVLI", "MOERDIJK": "NLMOE",
    "ANTWERP": "BEANR", "ANTWERPEN": "BEANR", "ANTWERPEN-BRUGGE": "BEANR", "ZEEBRUGGE": "BEZEE",
    "HAMBURG": "DEHAM", "BREMERHAVEN": "DEBRV", "LE HAVRE": "FRLEH",
}  # fmt: skip


def port_locode(name):
    clean = re.sub(r"[,(].*$", "", (name or "").upper()).strip()
    if re.fullmatch(r"[A-Z]{2}\s?[A-Z0-9]{3}", clean):
        return clean.replace(" ", "")
    return PORT_LOCODES.get(clean, "")


def merge_layout(data, layout):
    """Waarden die via de opmaak (label boven waarde) zijn gevonden gaan voor op losse tekstpatronen."""
    for field in ("bl_number", "booking_number", "vessel_name", "voyage", "port_of_loading", "port_of_discharge"):
        value = (layout.get(field) or "").strip()
        if field in {"bl_number", "booking_number", "voyage"}:
            value = value.split()[0] if value else ""
            if not re.fullmatch(r"(?=.*\d)[A-Z0-9\-/]{4,30}", value.upper()):
                continue
        if value:
            data[field] = value.upper()[:150]
    for field in ("consignee", "notify", "shipper"):
        if layout.get(field):
            data[field] = layout[field]
    if data.get("port_of_discharge"):
        data["port_of_discharge"] = port_locode(data["port_of_discharge"]) or data["port_of_discharge"]
    return data


def _goods_line(text):
    """Zonder label: de eerste regel die naar een levensmiddel/lading klinkt (FROZEN ..., CHILLED ...)."""
    for line in (text or "").splitlines():
        if GOODS_KEYWORDS.search(line) and not re.search(r"\b(?:CONTAINER|STOWED|TEMPERATURE|REEFER)\b", line, re.I):
            return re.sub(r"[\s\-:]+$", "", line.strip())[:250]
    return ""


def _normalize_name(value):
    value = re.sub(r"[^A-Z0-9 ]", " ", (value or "").upper().replace(".", ""))
    value = re.sub(r"\b(?:BV|B V|NV|VOF|GMBH|LTD|LIMITED|SA|S A|SL|SRL|SPA|INC|LLC|CO|HOLDING)\b", " ", value)
    return " ".join(value.split())


def match_customer(text, data):
    """Zoek de klant: eerst in de consignee, dan in de notify party, dan in de hele tekst."""
    from core.models import Customer

    customers = [(c.id, _normalize_name(c.name)) for c in Customer.objects.filter(active=True)]
    customers = [(cid, name) for cid, name in customers if len(name) >= 4]
    for block in (data.get("consignee"), data.get("notify"), text):
        haystack = f" {_normalize_name(block)} "
        hits = [(cid, name) for cid, name in customers if f" {name} " in haystack]
        if hits:
            return max(hits, key=lambda item: len(item[1]))[0]
    return None


def match_master_data(text, data):
    """Herken klant, rederij en keurpunt aan de hand van namen/SCAC in de tekst."""
    from core.models import InspectionPoint, ShippingLine

    upper = (text or "").upper()
    # De scheepsnaam ("MAERSK LONDRINA") zegt niets over de rederij die de B/L uitgeeft.
    if data.get("vessel_name"):
        upper = upper.replace(data["vessel_name"].upper(), " ")
    lines = list(ShippingLine.objects.filter(active=True))
    line_id, best = None, 0
    bl_prefix = (data.get("bl_number") or "")[:4].upper()
    for line in lines:
        names = [line.name.upper()] + ([line.scac.upper()] if line.scac else [])
        score = sum(len(re.findall(rf"\b{re.escape(n)}\b", upper)) for n in names)
        if line.scac and line.scac.upper() == bl_prefix:
            score += 100
        if score > best:
            line_id, best = line.id, score
    if line_id is None:
        # Containerprefix (bijv. MSKU/MAEU) wijst vaak op de rederij.
        prefixes = {c["container_number"][:4] for c in data.get("containers", [])}
        for line in lines:
            if line.scac and line.scac.upper() in prefixes:
                line_id = line.id
                break
    point_id = None
    for point in InspectionPoint.objects.filter(active=True):
        if point.name.upper() in upper or (point.traces_code and point.traces_code.upper() in upper):
            point_id = point.id
            break
    data["shipping_line_id"] = line_id
    data["inspection_point_id"] = point_id
    data["customer_id"] = match_customer(text, data)
    return data


def process_document(document):
    """Lees een geüpload document uit en sla tekst en gevonden velden op."""
    from .layout import pdf_layout_fields

    layout = {}
    try:
        with document.local_file() as path:
            text, method = extract_text(path)
            if method == "pdf-tekst":
                try:
                    layout = pdf_layout_fields(path)
                except Exception:  # noqa: BLE001 - opmaakherkenning is een extraatje; tekstherkenning blijft staan
                    layout = {}
    except Exception as exc:  # noqa: BLE001 - ook een kapotte of beveiligde PDF: het document blijft bewaard
        known = isinstance(exc, (ExtractionError, FileNotFoundError))
        document.status = "fout"
        document.error = (str(exc) if known else f"Bestand kon niet worden gelezen ({exc.__class__.__name__}).")[:300]
        document.save(update_fields=["status", "error", "updated_at"])
        return document
    data = merge_layout(extract_fields(text), layout)
    data = match_master_data(text, data)
    document.extracted_text = text
    document.extraction_method = method
    document.extracted_data = data
    document.status = "verwerkt"
    document.error = ""
    document.save()
    return document
