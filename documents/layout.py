"""Velden uitlezen op basis van de opmaak van een PDF (label met de waarde eronder).

Veel B/L's en sea waybills (CMA CGM, Hapag, MSC, ...) zijn een raster van vakjes: bovenin
een klein label ("VESSEL", "PORT OF LOADING", "WAYBILL NUMBER") en daaronder de waarde.
In platte tekst staan labels en waarden dan op aparte regels door elkaar
("VESSEL PORT OF LOADING PORT OF DISCHARGE" / "MAERSK LONDRINA PARANAGUA ROTTERDAM").
Met de posities van de woorden kunnen we elke waarde aan het juiste label koppelen.
"""

import re

# veld -> labels (langste eerst wordt automatisch geregeld)
FIELD_LABELS = {
    "voyage": ["VOYAGE NUMBER", "VOYAGE NO", "VOYAGE NR", "VOY NO", "VOYAGE"],
    "bl_number": [
        "WAYBILL NUMBER", "WAYBILL NO", "SEA WAYBILL NO", "SWB NO", "B/L NUMBER", "B/L NO", "B/L NR",
        "BILL OF LADING NUMBER", "BILL OF LADING NO", "BL NUMBER", "BL NO",
    ],
    "booking_number": ["BOOKING NUMBER", "BOOKING NO", "BOOKING REF", "BOOKING REFERENCE"],
    "vessel_name": ["OCEAN VESSEL", "VESSEL NAME", "VESSEL"],
    "port_of_loading": ["PORT OF LOADING"],
    "port_of_discharge": ["PORT OF DISCHARGE"],
    "consignee": ["CONSIGNEE"],
    "notify": ["NOTIFY PARTY", "NOTIFY"],
    "shipper": ["SHIPPER", "SHIPPER/EXPORTER"],
}  # fmt: skip
# Labels die we niet uitlezen, maar die wel een kolom afbakenen.
OTHER_LABELS = [
    "PRE CARRIAGE BY", "PLACE OF RECEIPT", "FREIGHT TO BE PAID AT", "FREIGHT PAYABLE AT", "NUMBER OF ORIGINAL WAYBILLS",
    "NUMBER OF ORIGINAL B/L", "NUMBER OF ORIGINAL BILLS OF LADING", "FINAL PLACE OF DELIVERY", "PLACE OF DELIVERY",
    "EXPORT REFERENCES", "FORWARDING AGENT", "MARKS AND NOS", "NON NEGOTIABLE", "GROSS WEIGHT", "MEASUREMENT", "TARE",
    "PLACE AND DATE OF ISSUE", "CARRIER",
]  # fmt: skip
MULTILINE_FIELDS = {"consignee", "notify", "shipper"}
LINE_TOLERANCE = 3.5  # pt: woorden binnen deze hoogte horen bij dezelfde regel
VALUE_WINDOW = 24  # pt: waarde moet binnen deze afstand onder het label beginnen
CLUSTER_GAP = 12  # pt: grotere horizontale tussenruimte = ander vak
MAX_COLUMN_DISTANCE = 25  # pt: zo ver mag een waarde naast zijn label beginnen


def _norm(word):
    return word.upper().strip("*:.,;()")


def _label_patterns():
    labels = [(label, field) for field, items in FIELD_LABELS.items() for label in items]
    labels += [(label, None) for label in OTHER_LABELS]
    labels.sort(key=lambda item: -len(item[0].split()))
    return [(label.split(), field) for label, field in labels]


LABELS = _label_patterns()


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


def _find_labels(lines):
    """Zoek labels per regel. Geeft lijst van dicts met field, x0, x1, top, bottom, en markeert labelwoorden."""
    found = []
    for line in lines:
        words = line["words"]
        i = 0
        while i < len(words):
            for parts, field in LABELS:
                chunk = words[i : i + len(parts)]
                if len(chunk) == len(parts) and [_norm(w["text"]) for w in chunk] == parts:
                    # Labels staan in kleine hoofdletters; lopende tekst ("any Vessel") telt niet.
                    if any(w["text"] != w["text"].upper() for w in chunk):
                        continue
                    for w in chunk:
                        w["is_label"] = True
                    found.append({
                        "field": field, "x0": chunk[0]["x0"], "x1": chunk[-1]["x1"],
                        "top": min(w["top"] for w in chunk), "bottom": max(w["bottom"] for w in chunk),
                    })
                    i += len(parts)
                    break
            else:
                i += 1
    return found


def _clusters(words):
    clusters = []
    for word in words:
        if clusters and word["x0"] - clusters[-1][-1]["x1"] <= CLUSTER_GAP:
            clusters[-1].append(word)
        else:
            clusters.append([word])
    return [
        {"text": " ".join(w["text"] for w in c), "x0": c[0]["x0"], "x1": c[-1]["x1"], "top": c[0]["top"], "bottom": max(w["bottom"] for w in c)}
        for c in clusters
    ]


def _distance(a, b):
    if a["x1"] < b["x0"]:
        return b["x0"] - a["x1"]
    if b["x1"] < a["x0"]:
        return a["x0"] - b["x1"]
    return 0


def _value_for(label, labels, lines):
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
            if values:
                break
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
        words = [dict(w) for w in words]
        lines = _group_lines(words)
        labels = _find_labels(lines)
        for label in labels:
            field = label["field"]
            if not field or field in result:
                continue
            values = _value_for(label, labels, lines)
            if values:
                result[field] = "\n".join(values) if field in MULTILINE_FIELDS else values[0]
    return {k: re.sub(r"\s+\*$", "", v).strip() for k, v in result.items()}


def pdf_layout_fields(path):
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        return extract_layout_fields([page.extract_words() for page in pdf.pages[:3]])
