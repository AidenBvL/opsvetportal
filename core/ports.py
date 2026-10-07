"""Havencodes (UN/LOCODE): namen als "PARANAGUA (BR)" of "Rotterdam, Netherlands" omzetten naar BRPNG / NLRTM.

Dossiers bewaren altijd de code (dat verwachten ook de trackingdiensten); op het scherm tonen
we "Paranaguá (BRPNG)". Onbekende havens blijven staan zoals ze binnenkwamen en kun je
toevoegen onder Stamgegevens > Havens; daarna worden open dossiers met die naam bijgewerkt.
"""

import re
import time
import unicodedata

# (UN/LOCODE, naam, andere schrijfwijzen) — beginvulling van Stamgegevens > Havens.
DEFAULT_PORTS = [
    ("NLRTM", "Rotterdam", "MAASVLAKTE, EUROPOORT"), ("NLAMS", "Amsterdam", ""), ("NLVLI", "Vlissingen", "FLUSHING"),
    ("NLMOE", "Moerdijk", ""), ("NLTNZ", "Terneuzen", ""), ("NLEEM", "Eemshaven", ""), ("NLDZL", "Delfzijl", ""),
    ("BEANR", "Antwerpen", "ANTWERP, ANVERS, ANTWERPEN-BRUGGE"), ("BEZEE", "Zeebrugge", ""), ("BEGNE", "Gent", "GHENT"),
    ("DEHAM", "Hamburg", ""), ("DEBRV", "Bremerhaven", ""), ("DEWVN", "Wilhelmshaven", ""),
    ("FRLEH", "Le Havre", ""), ("FRDKK", "Dunkerque", "DUNKIRK"), ("FRFOS", "Fos-sur-Mer", "FOS"), ("FRMRS", "Marseille", ""),
    ("GBFXT", "Felixstowe", ""), ("GBSOU", "Southampton", ""), ("GBLGP", "London Gateway", ""), ("GBTIL", "Tilbury", ""),
    ("GBLIV", "Liverpool", ""), ("IEDUB", "Dublin", ""),
    ("ESALG", "Algeciras", ""), ("ESVLC", "Valencia", ""), ("ESBCN", "Barcelona", ""), ("ESVGO", "Vigo", ""), ("ESBIO", "Bilbao", ""),
    ("PTLEI", "Leixões", "LEIXOES, PORTO, OPORTO"), ("PTLIS", "Lisboa", "LISBON"), ("PTSIE", "Sines", ""),
    ("ITGOA", "Genova", "GENOA"), ("ITSPE", "La Spezia", ""), ("ITGIT", "Gioia Tauro", ""), ("ITLIV", "Livorno", "LEGHORN"),
    ("ITSAL", "Salerno", ""), ("GRPIR", "Piraeus", "PIREAS"), ("TRMER", "Mersin", ""), ("TRIZM", "Izmir", ""),
    ("MAPTM", "Tanger Med", "TANGIER MED, TANGER MEDITERRANEE"), ("MACAS", "Casablanca", ""), ("MAAGA", "Agadir", ""),
    ("EGPSD", "Port Said", ""), ("EGDAM", "Damietta", ""), ("EGALY", "Alexandria", ""),
    ("PLGDN", "Gdansk", ""), ("PLGDY", "Gdynia", ""), ("SEGOT", "Göteborg", "GOTHENBURG"), ("DKAAR", "Aarhus", ""),
    ("NOAES", "Ålesund", "AALESUND"), ("NOOSL", "Oslo", ""), ("ISREY", "Reykjavik", ""),
    ("BRPNG", "Paranaguá", ""), ("BRSSZ", "Santos", ""), ("BRITJ", "Itajaí", ""), ("BRNVT", "Navegantes", ""),
    ("BRIOA", "Itapoá", ""), ("BRRIG", "Rio Grande", ""), ("BRRIO", "Rio de Janeiro", ""), ("BRSSA", "Salvador", ""),
    ("BRSUA", "Suape", ""), ("BRPEC", "Pecém", ""), ("BRVIX", "Vitória", ""), ("BRIBB", "Imbituba", ""),
    ("BRSFS", "São Francisco do Sul", ""),
    ("ARBUE", "Buenos Aires", ""), ("UYMVD", "Montevideo", ""), ("CLSAI", "San Antonio", ""), ("CLVAP", "Valparaíso", ""),
    ("CLSVE", "San Vicente", ""), ("CLCNL", "Coronel", ""), ("PECLL", "Callao", ""), ("PEPAI", "Paita", ""),
    ("ECGYE", "Guayaquil", ""), ("ECPSJ", "Posorja", ""), ("ECPBO", "Puerto Bolívar", ""),
    ("COCTG", "Cartagena", ""), ("COSMR", "Santa Marta", ""), ("COTRB", "Turbo", ""), ("COBUN", "Buenaventura", ""),
    ("CRMOB", "Moín", ""), ("CRLIO", "Puerto Limón", "LIMON"), ("PAMIT", "Manzanillo", ""), ("PABLB", "Balboa", ""),
    ("GTPRQ", "Puerto Quetzal", ""), ("GTSTC", "Santo Tomás de Castilla", ""), ("HNPCR", "Puerto Cortés", ""),
    ("MXZLO", "Manzanillo", ""), ("MXVER", "Veracruz", ""), ("MXLZC", "Lázaro Cárdenas", ""), ("DOCAU", "Caucedo", ""),
    ("USNYC", "New York", "NEW YORK/NEWARK, NEWARK"), ("USSAV", "Savannah", ""), ("USPHL", "Philadelphia", ""),
    ("USHOU", "Houston", ""), ("USLAX", "Los Angeles", ""), ("USLGB", "Long Beach", ""), ("USSEA", "Seattle", ""),
    ("USMIA", "Miami", ""), ("USCHS", "Charleston", ""), ("USORF", "Norfolk", ""), ("USBAL", "Baltimore", ""),
    ("CAHAL", "Halifax", ""), ("CAMTR", "Montréal", ""), ("CAVAN", "Vancouver", ""), ("CAPRR", "Prince Rupert", ""),
    ("ZADUR", "Durban", ""), ("ZACPT", "Cape Town", "KAAPSTAD"), ("ZAPLZ", "Port Elizabeth", "GQEBERHA"),
    ("ZAZBA", "Coega", "NGQURA"), ("NAWVB", "Walvis Bay", ""), ("KEMBA", "Mombasa", ""), ("TZDAR", "Dar es Salaam", ""),
    ("MUPLU", "Port Louis", ""), ("CIABJ", "Abidjan", ""), ("CISPY", "San Pedro", ""), ("GHTEM", "Tema", ""),
    ("SNDKR", "Dakar", ""), ("NGAPP", "Apapa", "LAGOS"), ("MRNDB", "Nouadhibou", ""),
    ("INNSA", "Nhava Sheva", "JAWAHARLAL NEHRU, JNPT"), ("INMUN", "Mundra", ""), ("INMAA", "Chennai", "MADRAS"),
    ("INCOK", "Kochi", "COCHIN"), ("INVTZ", "Visakhapatnam", "VIZAG"), ("INPAV", "Pipavav", ""),
    ("BDCGP", "Chittagong", "CHATTOGRAM"), ("LKCMB", "Colombo", ""), ("PKKHI", "Karachi", ""), ("PKBQM", "Port Qasim", "MUHAMMAD BIN QASIM"),
    ("AEJEA", "Jebel Ali", "DUBAI"), ("SAJED", "Jeddah", ""), ("SADMM", "Dammam", ""), ("OMSLL", "Salalah", ""),
    ("SGSIN", "Singapore", "SINGAPORE"), ("MYPKG", "Port Klang", ""), ("MYTPP", "Tanjung Pelepas", ""),
    ("IDJKT", "Jakarta", "TANJUNG PRIOK"), ("IDSUB", "Surabaya", ""), ("IDBLW", "Belawan", ""),
    ("THLCH", "Laem Chabang", ""), ("THBKK", "Bangkok", ""),
    ("VNSGN", "Ho Chi Minh", "HO CHI MINH CITY, SAIGON"), ("VNCMT", "Cai Mep", ""), ("VNHPH", "Haiphong", "HAI PHONG"),
    ("VNDAD", "Da Nang", "DANANG"), ("PHMNL", "Manila", ""),
    ("CNSHA", "Shanghai", ""), ("CNNGB", "Ningbo", ""), ("CNTAO", "Qingdao", ""), ("CNXMN", "Xiamen", ""),
    ("CNYTN", "Yantian", ""), ("CNSHK", "Shekou", ""), ("CNNSA", "Nansha", ""), ("CNDLC", "Dalian", ""),
    ("CNTXG", "Tianjin", "XINGANG, TIANJIN XINGANG"), ("CNFOC", "Fuzhou", ""), ("CNLYG", "Lianyungang", ""),
    ("HKHKG", "Hong Kong", ""), ("TWKHH", "Kaohsiung", ""), ("KRPUS", "Busan", "PUSAN"),
    ("JPTYO", "Tokyo", ""), ("JPYOK", "Yokohama", ""), ("JPUKB", "Kobe", ""), ("JPNGO", "Nagoya", ""), ("JPOSA", "Osaka", ""),
    ("AUMEL", "Melbourne", ""), ("AUSYD", "Sydney", ""), ("AUBNE", "Brisbane", ""), ("AUFRE", "Fremantle", ""),
    ("AUADL", "Adelaide", ""), ("NZAKL", "Auckland", ""), ("NZTRG", "Tauranga", ""), ("NZNPE", "Napier", ""),
    ("NZLYT", "Lyttelton", ""),
]  # fmt: skip

# Landnamen zoals ze achter een havennaam staan ("ROTTERDAM, NETHERLANDS") -> landcode
COUNTRIES = {
    "NETHERLANDS": "NL", "THE NETHERLANDS": "NL", "NEDERLAND": "NL", "HOLLAND": "NL", "BELGIUM": "BE", "BELGIE": "BE",
    "GERMANY": "DE", "FRANCE": "FR", "UNITED KINGDOM": "GB", "UK": "GB", "SPAIN": "ES", "PORTUGAL": "PT", "ITALY": "IT",
    "BRAZIL": "BR", "BRASIL": "BR", "ARGENTINA": "AR", "URUGUAY": "UY", "CHILE": "CL", "PERU": "PE", "ECUADOR": "EC",
    "COLOMBIA": "CO", "COSTA RICA": "CR", "PANAMA": "PA", "MEXICO": "MX", "USA": "US", "UNITED STATES": "US",
    "CANADA": "CA", "SOUTH AFRICA": "ZA", "INDIA": "IN", "CHINA": "CN", "VIETNAM": "VN", "VIET NAM": "VN",
    "THAILAND": "TH", "INDONESIA": "ID", "MALAYSIA": "MY", "NEW ZEALAND": "NZ", "AUSTRALIA": "AU", "MOROCCO": "MA",
}  # fmt: skip

# Terminals die eerder met de hand waren ingevoerd -> (haven, SMDG-code). Bij de import worden ze die terminal.
DEFAULT_TERMINALS = [
    ("ECT Delta Terminal", "NLRTM", "ECT DELTA, HUTCHISON PORTS ECT DELTA, ECT DELTA ROTTERDAM, DELTA TERMINAL"),
    ("ECT Euromax Terminal", "NLRTM", "ECT EUROMAX, ECT EUROMAX ROTTERDAM, EUROMAX, EUROMAX TERMINAL ROTTERDAM"),
    ("Hutchison Ports Delta II", "NLRTM", "HUTCHISON PORT DELTA II, HUTCHISON PORTS DELTA 2, DELTA II"),
    ("APM Terminals Maasvlakte II", "NLRTM", "APMT MVII, APMT MAASVLAKTE II, APM TERMINALS MVII, APM TERMINALS MAASVLAKTE 2"),
    ("APM Terminals Rotterdam", "NLRTM", "APMT ROTTERDAM, APM TERMINALS MAASVLAKTE"),
    ("Rotterdam World Gateway", "NLRTM", "RWG, ROTTERDAM WORLD GATEWAY TERMINAL"),
    ("MPET (MSC PSA European Terminal)", "BEANR", "MPET, MSC PSA EUROPEAN TERMINAL, PSA MPET"),
    ("PSA Noordzee Terminal", "BEANR", "NOORDZEE TERMINAL, PSA NOORDZEE"),
    ("PSA Europa Terminal", "BEANR", "EUROPA TERMINAL, PSA EUROPA"),
    ("DP World Antwerp Gateway", "BEANR", "ANTWERP GATEWAY, DP WORLD ANTWERP"),
    ("HHLA Container Terminal Burchardkai", "DEHAM", "CTB, BURCHARDKAI, HHLA CTB"),
    ("HHLA Container Terminal Altenwerder", "DEHAM", "CTA, ALTENWERDER, HHLA CTA"),
    ("Eurogate Container Terminal Hamburg", "DEHAM", "EUROGATE HAMBURG, CTH"),
    ("North Sea Terminal Bremerhaven", "DEBRV", "NTB, NORTH SEA TERMINAL"),
    ("Eurogate Container Terminal Bremerhaven", "DEBRV", "EUROGATE BREMERHAVEN, CTB BREMERHAVEN"),
]  # fmt: skip
LEGACY_TERMINAL_CODES = {
    "ECT Delta Terminal": "DCD", "ECT Euromax Terminal": "EMX", "Hutchison Ports Delta II": "HPD2",
    "APM Terminals Maasvlakte II": "NLMVII", "Rotterdam World Gateway": "RWG", "MPET (MSC PSA European Terminal)": "K1718",
    "PSA Noordzee Terminal": "K913", "PSA Europa Terminal": "K869", "DP World Antwerp Gateway": "1700",
    "HHLA Container Terminal Burchardkai": "CTB", "HHLA Container Terminal Altenwerder": "CTA",
    "Eurogate Container Terminal Hamburg": "EGH", "North Sea Terminal Bremerhaven": "NTB",
    "Eurogate Container Terminal Bremerhaven": "EGB",
}  # fmt: skip

from .data.countries import COUNTRY_NAMES  # noqa: E402

LOCODE_RE = re.compile(r"[A-Z]{2}[A-Z0-9]{3}")
_cache = {"at": 0.0, "index": None}
CACHE_SECONDS = 300


def _key(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c)).upper()
    value = re.sub(r"[^A-Z0-9 ]", " ", value)
    return " ".join(value.split())


def clear_cache():
    _cache["index"] = None


GENERIC_WORDS = {"TERMINAL", "TERMINALS", "CONTAINER", "CONTAINERS", "PORT", "PORTS", "THE", "OF", "DE", "AND", "INTERNATIONAL"}


def _words(value):
    """Woorden voor vergelijken, enkelvoud: "HUTCHISON PORTS" en "HUTCHISON PORT" zijn gelijk."""
    return {w[:-1] if len(w) > 3 and w.endswith("S") else w for w in _key(value).split()}


def _load_terminals(Terminal):
    from django.db import DatabaseError, transaction

    try:
        with transaction.atomic():  # tijdens oudere migraties bestaan (een deel van) de kolommen nog niet
            return list(Terminal.objects.filter(active=True).values_list("name", "aliases", "code", "port__locode", "port__name", "company"))
    except DatabaseError:
        pass
    try:
        with transaction.atomic():
            return [(n, a, "", "", "", "") for n, a in Terminal.objects.filter(active=True).values_list("name", "aliases")]
    except DatabaseError:
        return []


def port_index():
    """Havens en terminals uit de stamgegevens, kort in het geheugen.

    names: {naam: [codes]}, codes: {code: naam}, container: {codes van containerhavens},
    terminals: [{label, locode, words}], terminal_keys: {naam/alias/code: [posities in terminals]}.
    """
    if _cache["index"] is not None and time.monotonic() - _cache["at"] < CACHE_SECONDS:
        return _cache["index"]
    from django.db import DatabaseError, transaction

    from .models import Port, Terminal

    names, codes, container = {}, {}, set()
    for locode, name, aliases in Port.objects.filter(active=True).values_list("locode", "name", "aliases"):
        codes[locode] = name
        for alias in [name, *aliases.split(",")]:
            if _key(alias):
                names.setdefault(_key(alias), [])
                if locode not in names[_key(alias)]:
                    names[_key(alias)].append(locode)
    try:
        with transaction.atomic():
            container = set(Port.objects.filter(active=True, container_port=True).values_list("locode", flat=True))
    except DatabaseError:
        container = {code for code, _name, _aliases in DEFAULT_PORTS}

    terminals, terminal_keys = [], {}
    for name, aliases, code, locode, port_name, company in _load_terminals(Terminal):
        label = f"{name} ({code})" if code and f"({code})" not in name else name
        entry = {"label": label, "name": name, "code": code, "locode": locode or "",
                 "words": _words(f"{name} {company} {port_name} {code}")}
        position = len(terminals)
        terminals.append(entry)
        keys = [label, name, *aliases.split(",")]
        if code and len(code) >= 3:
            keys.append(code)
        for alias in keys:
            if _key(alias):
                terminal_keys.setdefault(_key(alias), [])
                if position not in terminal_keys[_key(alias)]:
                    terminal_keys[_key(alias)].append(position)
    _cache.update(at=time.monotonic(), index={
        "names": names, "codes": codes, "container": container, "terminals": terminals, "terminal_keys": terminal_keys,
        "with_terminals": {t["locode"] for t in terminals if t["locode"]},
    })
    return _cache["index"]


def split_country(value):
    """"PARANAGUA (BR)" -> ("PARANAGUA", "BR"); "Rotterdam, Netherlands" -> ("Rotterdam", "NL")."""
    value = (value or "").strip()
    country = ""
    match = re.search(r"\(\s*([A-Za-z]{2})\s*\)\s*$", value)
    if match:
        country, value = match.group(1).upper(), value[: match.start()]
    if "," in value:
        head, tail = value.split(",", 1)
        tail_key = _key(tail)
        country = country or COUNTRIES.get(tail_key, tail_key if re.fullmatch(r"[A-Z]{2}", tail_key) else "")
        value = head
    value = re.sub(r"^\s*PORT\s+OF\s+", "", value, flags=re.I)
    return value.strip(), country


def port_code(value):
    """Geeft de UN/LOCODE terug als de haven bekend is (of al een code is), anders de invoer ongewijzigd."""
    raw = (value or "").strip()
    if not raw:
        return ""
    index = port_index()
    compact = raw.replace(" ", "").upper()
    if compact in index["codes"]:
        return compact
    name, country = split_country(raw)
    candidates = index["names"].get(_key(name)) or index["names"].get(_key(raw)) or []
    if country:
        candidates = [c for c in candidates if c.startswith(country)] or candidates
    if len(candidates) > 1:
        # Meerdere havens met deze naam: een containerhaven gaat voor (als dat er precies één is).
        for preferred in (index["container"], index["with_terminals"]):
            main = [c for c in candidates if c in preferred]
            if main:
                candidates = main
            if len(candidates) == 1:
                break
    if len(candidates) == 1 or (candidates and country):
        return candidates[0]
    # Een onbekende code met spatie of cijfer ("NL RTM", "DE2XX") is duidelijk een code.
    if LOCODE_RE.fullmatch(compact) and (" " in raw or any(ch.isdigit() for ch in compact)):
        return compact
    return raw


def _words_match(words, terminal_words):
    """Elk woord moet voorkomen, of een afkorting zijn ("CONT" -> CONTEINERES); korte/algemene woorden mogen ontbreken."""
    distinctive = 0
    for word in words:
        if word in terminal_words or (len(word) >= 4 and any(t.startswith(word) for t in terminal_words)):
            distinctive += word not in GENERIC_WORDS and len(word) >= 3
        elif len(word) > 3 and word not in GENERIC_WORDS:
            return False
    return distinctive >= 2


def find_terminal(value, port=""):
    """Zoek een terminal bij een naam zoals een rederij die schrijft. Eerst exact (naam, code, andere schrijfwijze),
    anders op woorden: alle woorden uit de invoer moeten in naam/bedrijf/haven van precies één terminal voorkomen."""
    raw = (value or "").strip()
    if not raw:
        return None
    index = port_index()
    terminals = index["terminals"]
    port = (port or "").upper()
    hits = [terminals[i] for i in index["terminal_keys"].get(_key(raw), [])]
    if not hits:
        words = _words(raw)
        if not words - GENERIC_WORDS:
            return None
        hits = [t for t in terminals if _words_match(words, t["words"])]
    if len(hits) > 1 and port:
        hits = [t for t in hits if t["locode"] == port] or hits
    return hits[0] if len(hits) == 1 else None


def terminal_name(value, port=""):
    """"ECT EUROMAX ROTTERDAM" -> "ECT EUROMAX TERMINAL (EMX)" als de terminal bekend is, anders ongewijzigd."""
    terminal = find_terminal(value, port)
    return terminal["label"] if terminal else (value or "").strip()


def terminal_label(value, port=""):
    """Voor op het scherm: "ECT EUROMAX TERMINAL (EMX) · Rotterdam, Nederland (NLRTM)"."""
    terminal = find_terminal(value, port)
    if not terminal:
        return (value or "").strip()
    return f"{terminal['label']} · {port_label(terminal['locode'])}" if terminal["locode"] else terminal["label"]


def port_full_name(code):
    """"BRPNG" -> "Paranaguá, Brazilië"; leeg als de code onbekend is."""
    code = (code or "").strip().upper()
    name = port_index()["codes"].get(code)
    if not name:
        return ""
    country = COUNTRY_NAMES.get(code[:2], code[:2])
    return name if _key(name) == _key(country) else f"{name}, {country}"


def port_label(value):
    """Voor op het scherm: "Paranaguá, Brazilië (BRPNG)"; onbekend blijft zoals het is."""
    value = (value or "").strip()
    full = port_full_name(value)
    return f"{full} ({value.upper()})" if full else value


def recode_shipments(open_only=True):
    """Dossiers met een havennaam i.p.v. code alsnog omzetten (bijv. nadat een haven is toegevoegd)."""
    from shipments.models import SeaShipment

    shipments = SeaShipment.objects.filter(status__in=SeaShipment.OPEN_STATUSES) if open_only else SeaShipment.objects.all()
    open_shipments = shipments.exclude(terminal="")
    for pk, value, pod in open_shipments.values_list("pk", "terminal", "port_of_discharge"):
        name = terminal_name(value, pod)
        if name != value:
            SeaShipment.objects.filter(pk=pk).update(terminal=name)

    for field in ("port_of_loading", "port_of_discharge"):
        rows = (shipments.exclude(**{f"{field}__regex": r"^[A-Z]{2}[A-Z0-9]{3}$"})
                .exclude(**{field: ""}).values_list("pk", field))
        for pk, value in rows:
            code = port_code(value)
            if code != value:
                SeaShipment.objects.filter(pk=pk).update(**{field: code})


def import_reference_data(Port, Terminal, log=print):
    """Havens (UN/LOCODE) en terminals (SMDG Terminal Code List) uit core/data/*.csv laden of bijwerken.

    Werkt met de gewone modellen en met de modellen in een migratie. Eigen aanvullingen (andere schrijfwijzen,
    zelf toegevoegde havens/terminals) blijven staan.
    """
    import csv
    from pathlib import Path

    folder = Path(__file__).parent / "data"
    with open(folder / "terminals.csv", encoding="utf-8") as fh:
        terminal_rows = list(csv.DictReader(fh))
    container_codes = {code for code, _n, _a in DEFAULT_PORTS} | {row["locode"] for row in terminal_rows}

    existing = set(Port.objects.values_list("locode", flat=True))
    new_ports = []
    with open(folder / "ports.csv", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["locode"] not in existing:
                new_ports.append(Port(locode=row["locode"], name=row["name"][:100], aliases=row["name_ascii"][:300],
                                      container_port=row["locode"] in container_codes))
    Port.objects.bulk_create(new_ports, batch_size=1000, ignore_conflicts=True)
    Port.objects.filter(locode__in=container_codes, container_port=False).update(container_port=True)
    ports = dict(Port.objects.values_list("locode", "pk"))

    by_code = {(t.port_id, t.code): t for t in Terminal.objects.exclude(code="")}
    legacy = {t.name: t for t in Terminal.objects.filter(code="", name__in=list(LEGACY_TERMINAL_CODES))}
    created = updated = 0
    for row in terminal_rows:
        port_id = ports.get(row["locode"])
        terminal = by_code.get((port_id, row["code"]))
        if terminal is None:
            old = next((t for name, t in legacy.items() if LEGACY_TERMINAL_CODES[name] == row["code"]
                        and t.port_id == port_id), None)
            if old is not None:
                # Eerder handmatig aangemaakt: de oude naam blijft een andere schrijfwijze.
                old.aliases = ", ".join(a for a in [old.name, old.aliases] if a)[:400]
                terminal = old
        values = {"name": row["name"][:150], "code": row["code"], "port_id": port_id, "company": row["company"][:150],
                  "address": row["address"][:250], "website": row["website"][:250]}
        if terminal is None:
            Terminal.objects.create(**values)
            created += 1
        else:
            for field, value in values.items():
                setattr(terminal, field, value)
            Terminal.objects.filter(pk=terminal.pk).update(aliases=terminal.aliases, **values)
            updated += 1
    clear_cache()
    log(f"Havens: {len(new_ports)} toegevoegd. Terminals: {created} toegevoegd, {updated} bijgewerkt.")
