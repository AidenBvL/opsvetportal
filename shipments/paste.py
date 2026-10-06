"""Trackinggegevens uitlezen uit tekst die van de trackingpagina van een rederij is gekopieerd.

Werkwijze voor de gebruiker: container opzoeken op de website van de rederij, de pagina
selecteren (Ctrl+A, Ctrl+C) en in het portaal plakken. Werkt voor de opmaak van onder meer
CMA CGM ("SCHIP ( REIS)") en voor algemene teksten met "Vessel:"/"Voyage:"/"ETA".
"""

import re
from datetime import datetime

from django.utils import timezone

from .tracking.base import Leg, TrackingResult

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "MRT": 3, "APR": 4, "MAY": 5, "MEI": 5, "JUN": 6, "JUL": 7,
    "AUG": 8, "SEP": 9, "OCT": 10, "OKT": 10, "NOV": 11, "DEC": 12,
}  # fmt: skip

DATE_RE = re.compile(
    r"(?P<d>\d{1,2})[-/ .](?P<m>[A-Za-z]{3,9}|\d{1,2})[-/ .,]+(?P<y>\d{4})"
    r"(?:[^\d\n]{0,12}(?P<h>\d{1,2}):(?P<mi>\d{2})\s*(?P<ap>AM|PM)?)?",
    re.I,
)
ISO_RE = re.compile(r"(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})(?:[T ](?P<h>\d{2}):(?P<mi>\d{2}))?")
VESSEL_VOYAGE_RE = re.compile(r"^\s*(?P<vessel>[A-Z][A-Z0-9 .'\-]{2,40}?)\s*\(\s*(?P<voyage>[A-Z0-9]{3,14})\s*\)\s*$", re.M)


def _to_dt(match):
    if match is None:
        return None
    groups = match.groupdict()
    month = groups["m"]
    month = MONTHS.get(month[:3].upper()) if not month.isdigit() else int(month)
    if not month:
        return None
    hour, minute = int(groups.get("h") or 0), int(groups.get("mi") or 0)
    ap = (groups.get("ap") or "").upper()
    if ap == "PM" and hour < 12:
        hour += 12
    if ap == "AM" and hour == 12:
        hour = 0
    try:
        naive = datetime(int(groups["y"]), month, int(groups["d"]), hour, minute)
    except ValueError:
        return None
    # Rederijen tonen lokale tijden; voor een Nederlandse loshaven is dat Europe/Amsterdam.
    return timezone.make_aware(naive, timezone.get_current_timezone())


def _find_date(text):
    return _to_dt(DATE_RE.search(text)) or _to_dt(ISO_RE.search(text))


def _line_after(lines, label):
    for i, line in enumerate(lines):
        if line.strip().upper() == label and i + 1 < len(lines):
            return lines[i + 1].strip()
        match = re.match(rf"^\s*{label}\b[^:]*:\s*(.+)$", line, re.I)
        if match:
            return match.group(1).strip()
    return ""


def parse_tracking_text(text):
    """Geeft een TrackingResult terug, of None als er niets bruikbaars in de tekst staat."""
    text = (text or "").replace("\r", "")
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return None

    # ETA: zoek "ETA" en neem de eerste datum binnen de volgende paar regels.
    eta = None
    for i, line in enumerate(lines):
        if re.search(r"\bETA\b|estimated time of arrival|verwachte aankomst", line, re.I):
            eta = _find_date(" ".join(lines[i:i + 4]))
            if eta:
                break

    # Schip + reis: "COSCO SHIPPING GEMINI ( 0FAO2E1MA)" -> de laatste is de aankomst in de loshaven.
    vessel = voyage = terminal = ""
    ata = None
    matches = list(VESSEL_VOYAGE_RE.finditer(text))
    legs = []
    for match in matches:
        legs.append(Leg(vessel_name=match.group("vessel").strip(), voyage=match.group("voyage")))
    if matches:
        last = matches[-1]
        vessel, voyage = last.group("vessel").strip(), last.group("voyage")
        before = text[: last.start()].rstrip("\n").split("\n")
        block = [line.strip() for line in before[-5:] if line.strip()]
        if block:
            terminal = block[-1]
        block_text = " ".join(block)
        if re.search(r"arrival|arrived|aankomst", block_text, re.I) and not re.search(r"planned|estimated|expected|gepland", block_text, re.I):
            ata = _find_date(block_text)
            if ata and ata > timezone.now():
                ata = None
        if eta is None:
            eta = _find_date(block_text)
    else:
        vessel = _line_after(lines, "VESSEL") or _line_after(lines, "OCEAN VESSEL")
        voyage = _line_after(lines, "VOYAGE")
        match = re.match(r"(.+?)\s+(?:V\.?|VOY\.?)\s*([A-Z0-9]{3,12})$", vessel, re.I)
        if match:
            vessel, voyage = match.group(1), voyage or match.group(2)

    departed = None
    if matches:
        first = matches[0]
        block = " ".join(line.strip() for line in text[: first.start()].rstrip("\n").split("\n")[-5:])
        if re.search(r"departure|departed|vertrek", block, re.I) and not re.search(r"planned|estimated|gepland", block, re.I):
            departed = _find_date(block)
            if departed and departed > timezone.now():
                departed = None

    pol = _line_after(lines, "POL") or _line_after(lines, "PORT OF LOADING")
    pol = re.sub(r"\s*\([A-Z]{2}\)\s*$", "", pol).title() if pol else ""
    if not (eta or vessel):
        return None
    return TrackingResult(
        provider="geplakt",
        eta=ata or eta,
        ata=ata,
        vessel_name=vessel.upper()[:150],
        voyage=voyage.upper()[:40],
        legs=legs,
        raw={"bron": "geplakte tekst", "lengte": len(text)},
        port_of_loading=pol[:100],
        terminal=terminal[:100] if terminal and not DATE_RE.search(terminal) else "",
        departed_at=departed,
    )
