"""Velden uitlezen op basis van de opmaak van een PDF: een label met de waarde ernaast of eronder.

B/L's en sea waybills zijn een raster van vakjes met bovenin een klein label en daaronder de
waarde, of een regel "Label: waarde". Elke rederij noemt de labels net anders
("VESSEL", "Vessel(s):", "Ocean Vessel"; "WAYBILL NUMBER", "SWB-No.:", "B/L No."). Daarom
werkt dit niet met een vaste lijst per rederij, maar in twee stappen:

1. Labels vinden: een woordgroep die eindigt op ':' ("Port of Loading:"), of een kolomkop in
   hoofdletters uit de gangbare B/L-woordenschat ("PORT OF DISCHARGE", "VOYAGE NUMBER").
2. Betekenis bepalen uit de woorden in het label: iets met LOADING is de laadhaven, iets met
   VESSEL het schip, B/L / WAYBILL / SWB + NO/NUMBER het B/L-nummer, enzovoort.

De waarde is wat direct rechts van een 'Label:' staat, of anders wat direct onder het label in
dezelfde kolom staat (met de posities van de woorden; buurlabels bakenen de kolommen af).
"""

import re

# Kolomkoppen zonder dubbele punt (meestal in hoofdletters). Alleen nodig om een regel als
# "VESSEL PORT OF LOADING PORT OF DISCHARGE" in losse labels te knippen; de betekenis komt uit FIELD_RULES.
HEADER_VOCABULARY = [
    "VOYAGE NUMBER", "VOYAGE NO", "VOYAGE NR", "VOY NO", "VOYAGE", "WAYBILL NUMBER", "WAYBILL NO", "SEA WAYBILL NO",
    "SWB NO", "B/L NUMBER", "B/L NO", "B/L NR", "BILL OF LADING NUMBER", "BILL OF LADING NO", "BL NUMBER", "BL NO",
    "BOOKING NUMBER", "BOOKING NO", "BOOKING REF", "BOOKING REFERENCE", "OCEAN VESSEL", "VESSEL NAME", "VESSEL",
    "VESSEL AND VOYAGE", "VESSEL / VOYAGE", "PORT OF LOADING", "PORT OF DISCHARGE", "CONSIGNEE", "NOTIFY PARTY", "NOTIFY",
    "SHIPPER", "SHIPPER/EXPORTER", "EXPORTER", "PRE CARRIAGE BY", "PRE-CARRIAGE BY", "PLACE OF RECEIPT",
    "FREIGHT TO BE PAID AT", "FREIGHT PAYABLE AT", "NUMBER OF ORIGINAL WAYBILLS", "NUMBER OF ORIGINAL B/L",
    "NUMBER OF ORIGINAL BILLS OF LADING", "FINAL PLACE OF DELIVERY", "PLACE OF DELIVERY", "FINAL DESTINATION",
    "EXPORT REFERENCES", "FORWARDING AGENT", "MARKS AND NOS", "NON NEGOTIABLE", "GROSS WEIGHT", "MEASUREMENT", "TARE",
    "PLACE AND DATE OF ISSUE", "CARRIER", "POL", "POD",
]  # fmt: skip

# (veld, labeltekst moet hierop passen, en mag hier niet op passen). Volgorde telt: eerste treffer wint.
FIELD_RULES = [
    ("customer_reference", r"\b(?:CONSIGNEE S?|CUSTOMER S?|YOUR) REF", None),
    ("booking_number", r"\bBOOKING\b|\bCARRIER S? REF", None),
    ("bl_number", r"\b(?:B/?L|WAYBILL|SWB|BILL OF LADING)\b.*\b(?:NO|NR|NUMBER)\b|^(?:B/?L|SWB)$", r"ORIGINAL|NUMBER OF"),
    ("vessel_voyage", r"\bVESSELS?\b.*\bVOY(?:AGE)?\b", None),
    ("voyage", r"\bVOY(?:AGE)?\b", None),
    ("vessel_name", r"\bVESSELS?\b", None),
    ("port_of_loading", r"\bLOADING\b|^POL$", r"\bPLACE\b|\bDATE\b"),
    ("port_of_discharge", r"\bDISCHARGE\b|^POD$", r"\bPLACE\b|\bDATE\b"),
    ("consignee", r"\bCONSIGNEE\b", None),
    ("notify", r"\bNOTIFY\b", None),
    ("shipper", r"\bSHIPPER\b|\bEXPORTER\b", r"STATED|DECLARED"),
]
MULTILINE_FIELDS = {"consignee", "notify", "shipper"}
LINE_TOLERANCE = 3.5  # pt: woorden binnen deze hoogte horen bij dezelfde regel
VALUE_WINDOW = 24  # pt: waarde moet binnen deze afstand onder het label beginnen
CLUSTER_GAP = 12  # pt: grotere horizontale tussenruimte = ander vak
MAX_COLUMN_DISTANCE = 25  # pt: zo ver mag een waarde naast zijn label beginnen
MAX_LABEL_WORDS = 9


def _key(text):
    """'Carrier’s Reference:' -> 'CARRIER S REFERENCE'; 'SWB-No.:' -> 'SWB NO'; 'B/L No' -> 'B/L NO'."""
    text = re.sub(r"[^A-Z0-9/]+", " ", (text or "").upper())
    return " ".join(text.split())


def classify(label_text):
    key = _key(label_text)
    for field, pattern, exclude in FIELD_RULES:
        if re.search(pattern, key) and not (exclude and re.search(exclude, key)):
            return field
    return None


VOCABULARY = sorted({tuple(_key(phrase).split()) for phrase in HEADER_VOCABULARY}, key=len, reverse=True)


def _group_lines(words):
    lines = []
    for word in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        for line in lines:
            if abs(line["top"] - word["top"]) <= LINE_TOLERANCE:
                line["words"].append(word)
                break
        else:
            lines.append({"top": word["top"], "words": [word]})
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
    lines.sort(key=lambda line: line["top"])
    return lines


def _split_gaps(words):
    groups = []
    for word in words:
        if groups and word["x0"] - groups[-1][-1]["x1"] <= CLUSTER_GAP:
            groups[-1].append(word)
        else:
            groups.append([word])
    return groups


def _make_label(chunk, colon):
    for w in chunk:
        w["is_label"] = True
    text = " ".join(w["text"] for w in chunk)
    return {
        "text": text, "field": classify(text), "colon": colon, "x0": chunk[0]["x0"], "x1": chunk[-1]["x1"],
        "top": min(w["top"] for w in chunk), "bottom": max(w["bottom"] for w in chunk),
    }


def _height(word):
    return max(word["bottom"] - word["top"], 0.1)


def _same_font(chunk, word):
    """Labels zijn meestal kleiner gedrukt dan de waarden ernaast."""
    return 0.77 < _height(word) / _height(chunk[-1]) < 1.3


def _vocabulary_suffix(chunk):
    for size in range(len(chunk), 1, -1):
        if tuple(_key(" ".join(w["text"] for w in chunk[-size:])).split()) in VOCABULARY:
            return chunk[-size:]
    return chunk[-1:]


def _colon_labels(line):
    """'Port of Loading:' / 'Carrier’s Reference: SWB-No.:' / 'SEALS :' -> labels die op ':' eindigen."""
    found = []
    for group in _split_gaps(line["words"]):
        start = 0
        for i, word in enumerate(group):
            if not word["text"].endswith(":"):
                continue
            chunk = group[start : i + 1]
            after_label = start > 0
            start = i + 1
            # Alleen de woorden in hetzelfde lettertype als het woord met ':' horen bij het label.
            while len(chunk) > 1 and not _same_font([chunk[-1]], chunk[0]):
                chunk = chunk[1:]
            if after_label and len(chunk) > 1:
                # "VESSEL NAME: COSCO SEINE VOYAGE:" -> de woorden ervoor zijn de waarde van het vorige label.
                chunk = _vocabulary_suffix(chunk)
            words_with_letters = [w for w in chunk if re.search(r"[A-Za-z]", w["text"])]
            if not words_with_letters or len(chunk) > MAX_LABEL_WORDS or not re.match(r"[A-Za-z(]", chunk[0]["text"]):
                continue
            found.append(_make_label(chunk, colon=True))
    return found


def _header_labels(line):
    """Kolomkoppen in hoofdletters zonder dubbele punt ("VESSEL PORT OF LOADING ...")."""
    found = []
    words = line["words"]
    i = 0
    while i < len(words):
        if words[i].get("is_label"):
            i += 1
            continue
        for parts in VOCABULARY:
            chunk = words[i : i + len(parts)]
            if len(chunk) != len(parts) or any(w.get("is_label") for w in chunk):
                continue
            if tuple(_key(" ".join(w["text"] for w in chunk)).split()) != parts:
                continue
            # Labels staan in hoofdletters; lopende tekst ("on any Vessel") telt niet.
            if any(w["text"] != w["text"].upper() for w in chunk):
                continue
            found.append(_make_label(chunk, colon=False))
            i += len(parts)
            break
        else:
            i += 1
    return found


def _find_labels(lines):
    found = []
    for line in lines:
        found += _colon_labels(line)
        found += _header_labels(line)
    return found


def _clusters(words):
    return [
        {"text": " ".join(w["text"] for w in c), "x0": c[0]["x0"], "x1": c[-1]["x1"], "top": c[0]["top"], "bottom": max(w["bottom"] for w in c)}
        for c in _split_gaps(words)
    ]


def _distance(a, b):
    if a["x1"] < b["x0"]:
        return b["x0"] - a["x1"]
    if b["x1"] < a["x0"]:
        return a["x0"] - b["x1"]
    return 0


def _value_right(label, lines):
    """'VESSEL NAME: COSCO SHIPPING SEINE VOYAGE: 6232N' -> 'COSCO SHIPPING SEINE'."""
    if not label["colon"]:
        return ""
    line = next((line for line in lines if abs(line["top"] - label["top"]) <= LINE_TOLERANCE), None)
    if line is None:
        return ""
    following = [w for w in line["words"] if w["x0"] >= label["x1"] - 0.5]
    value, last_x1 = [], label["x1"]
    for word in following:
        if word.get("is_label") or word["x0"] - last_x1 > CLUSTER_GAP:
            break
        value.append(word["text"])
        last_x1 = word["x1"]
    return " ".join(value)


def _value_below(label, labels, lines):
    siblings = [lab for lab in labels if lab is not label and abs(lab["top"] - label["top"]) <= LINE_TOLERANCE + 1]
    values, last_bottom = [], None
    for line in lines:
        if line["top"] <= label["bottom"] - 1:
            continue
        limit = label["bottom"] + VALUE_WINDOW if last_bottom is None else last_bottom + 6
        if line["top"] > limit:
            break
        candidates = []
        for cluster in _clusters([w for w in line["words"] if not w.get("is_label")]):
            own = _distance(cluster, label)
            if own <= MAX_COLUMN_DISTANCE and all(_distance(cluster, other) >= own for other in siblings):
                candidates.append((own, cluster))
        if not candidates:
            if values or any(w.get("is_label") and _distance(w, label) == 0 for w in line["words"]):
                break  # er staat een volgend label in deze kolom: het vak is leeg
            continue
        cluster = min(candidates, key=lambda item: item[0])[1]
        values.append(cluster["text"])
        if label["field"] not in MULTILINE_FIELDS or len(values) >= 4:
            break
        last_bottom = cluster["bottom"]
    return values


def extract_layout_fields(pages_words):
    """`pages_words`: per pagina de woorden zoals pdfplumber `extract_words()` ze geeft."""
    result = {}
    for words in pages_words:
        words = [dict(w) for w in words if w.get("upright", True)]
        lines = _group_lines(words)
        labels = _find_labels(lines)
        for label in sorted(labels, key=lambda lab: (lab["top"], lab["x0"])):
            field = label["field"]
            if not field or field in result:
                continue
            right = _value_right(label, lines)
            values = [right] if right else _value_below(label, labels, lines)
            if values:
                result[field] = "\n".join(values) if field in MULTILINE_FIELDS else values[0]
    result = {k: re.sub(r"[\s,*]+$", "", v).strip() for k, v in result.items()}
    if "vessel_voyage" in result:
        # "MAERSK HIDALGO 642W" of "MAERSK HIDALGO / 642W": laatste deel met een cijfer is de reis.
        match = re.match(r"(.+?)\s*/?\s+(?=\S*\d)(\S{3,12})$", result.pop("vessel_voyage"))
        if match:
            result.setdefault("vessel_name", match.group(1))
            result.setdefault("voyage", match.group(2))
    return result


def pdf_layout_fields(path):
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        return extract_layout_fields([page.extract_words() for page in pdf.pages[:3]])
