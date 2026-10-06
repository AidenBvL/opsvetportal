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


DATE_LINE_RE = re.compile(r"^\s*(?:[A-Za-z]{3,9},?\s+)?\d{1,2}[-/ .](?:[A-Za-z]{3,9}|\d{1,2})[-/ .,]+\d{4}\s*$")
TIME_LINE_RE = re.compile(r"^\s*\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\s*$", re.I)
PLANNED_RE = re.compile(r"planned|estimated|expected|scheduled|gepland|verwacht", re.I)


def parse_events(lines):
    """Bewegingen zoals CMA CGM ze toont: datum, tijd, omschrijving, plaats, terminal, (schip ( reis))."""
    events, current = [], None
    for line in lines:
        if DATE_LINE_RE.match(line):
            current = {"date_text": line.strip(), "lines": []}
            events.append(current)
        elif current is not None:
            if TIME_LINE_RE.match(line) and not current["lines"]:
                current["date_text"] += " " + line.strip()
            else:
                current["lines"].append(line.strip())
    result = []
    for event in events:
        when = _find_date(event["date_text"])
        body = [line for line in event["lines"] if line]
        if when is None or not body:
            continue
        vessel = next((VESSEL_VOYAGE_RE.match(line) for line in body if VESSEL_VOYAGE_RE.match(line)), None)
        places = [line for line in body[1:] if not VESSEL_VOYAGE_RE.match(line)]
        result.append({
            "when": when,
            "what": body[0],
            "location": places[0] if places else "",
            "terminal": places[1] if len(places) > 1 else "",
            "vessel": vessel.group("vessel").strip() if vessel else "",
            "voyage": vessel.group("voyage") if vessel else "",
            "planned": bool(PLANNED_RE.search(body[0])) or when > timezone.now(),
        })
    return result


def _is(event, pattern):
    return re.search(pattern, event["what"], re.I) is not None


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

    events = parse_events(lines)
    legs = [Leg(vessel_name=e["vessel"], voyage=e["voyage"], location=e["location"]) for e in events if e["vessel"]]
    vessel_events = [e for e in events if e["vessel"]]
    vessel = voyage = terminal = ""
    if vessel_events:
        last = vessel_events[-1]
        vessel, voyage, terminal = last["vessel"], last["voyage"], last["terminal"]
    else:
        vessel = _line_after(lines, "VESSEL") or _line_after(lines, "OCEAN VESSEL")
        voyage = _line_after(lines, "VOYAGE")
        match = re.match(r"(.+?)\s+(?:V\.?|VOY\.?)\s*([A-Z0-9]{3,12})$", vessel, re.I)
        if match:
            vessel, voyage = match.group(1), voyage or match.group(2)

    actual = [e for e in events if not e["planned"]]
    # Vertrek uit de laadhaven: de eerste echte vertrekmelding.
    departed = next((e["when"] for e in actual if _is(e, r"departure|departed|vertrek")), None)
    # Aankomst/lossen in de loshaven: na de laatste keer dat de container aan boord ging (overslag telt niet).
    last_loaded = max((i for i, e in enumerate(actual) if _is(e, r"loaded|departure|departed")), default=-1)
    after = actual[last_loaded + 1:]
    ata = next((e["when"] for e in after if _is(e, r"arrival|arrived|berth")), None)
    discharged = next((e["when"] for e in after if _is(e, r"discharg")), None)
    gate_out = next((e["when"] for e in after if _is(e, r"gate out.*(consignee|full)|delivered|picked up")), None)
    if ata is None:
        # Samenvatting bovenaan: "Arrived at POD / Sat 03-OCT-2026 / 05:26 PM".
        for i, line in enumerate(lines):
            if re.match(r"^\s*(arrived at pod|arrived|aangekomen)\b", line, re.I):
                ata = _find_date(" ".join(lines[i:i + 3]))
                break
    if ata and ata > timezone.now():
        ata = None
    planned_arrival = [e["when"] for e in events if e["planned"] and _is(e, r"arrival|berth")]
    eta = eta or (planned_arrival[-1] if planned_arrival else None)
    if ata and eta and eta > ata and not planned_arrival:
        eta = None

    pol = _line_after(lines, "POL") or _line_after(lines, "PORT OF LOADING")
    pod = _line_after(lines, "POD") or _line_after(lines, "PORT OF DISCHARGE")
    if not (eta or ata or vessel):
        return None
    return TrackingResult(
        provider="geplakt",
        eta=ata or eta,
        ata=ata,
        vessel_name=vessel.upper()[:150],
        voyage=voyage.upper()[:40],
        legs=legs,
        raw={"bron": "geplakte tekst", "lengte": len(text), "gate_out": gate_out.isoformat() if gate_out else None},
        port_of_loading=pol[:100],
        port_of_discharge=pod[:100],
        terminal=terminal[:100] if terminal and not DATE_RE.search(terminal) else "",
        departed_at=departed,
        discharged_at=discharged,
        gate_out_at=gate_out,
    )
