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

# (volledige naam, UN/LOCODE haven, andere schrijfwijzen) — beginvulling van Stamgegevens > Terminals.
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

# Landcode (eerste 2 letters van de UN/LOCODE) -> landnaam, voor "Paranaguá, Brazilië (BRPNG)".
COUNTRY_NAMES = {
    "NL": "Nederland", "BE": "België", "DE": "Duitsland", "FR": "Frankrijk", "GB": "Verenigd Koninkrijk", "IE": "Ierland",
    "ES": "Spanje", "PT": "Portugal", "IT": "Italië", "GR": "Griekenland", "TR": "Turkije", "MA": "Marokko", "EG": "Egypte",
    "PL": "Polen", "SE": "Zweden", "DK": "Denemarken", "NO": "Noorwegen", "IS": "IJsland", "FO": "Faeröer", "BR": "Brazilië",
    "AR": "Argentinië", "UY": "Uruguay", "CL": "Chili", "PE": "Peru", "EC": "Ecuador", "CO": "Colombia", "CR": "Costa Rica",
    "PA": "Panama", "GT": "Guatemala", "HN": "Honduras", "MX": "Mexico", "DO": "Dominicaanse Republiek",
    "US": "Verenigde Staten", "CA": "Canada", "ZA": "Zuid-Afrika", "NA": "Namibië", "KE": "Kenia", "TZ": "Tanzania",
    "MU": "Mauritius", "CI": "Ivoorkust", "GH": "Ghana", "SN": "Senegal", "NG": "Nigeria", "MR": "Mauritanië",
    "IN": "India", "BD": "Bangladesh", "LK": "Sri Lanka", "PK": "Pakistan", "AE": "Verenigde Arabische Emiraten",
    "SA": "Saoedi-Arabië", "OM": "Oman", "SG": "Singapore", "MY": "Maleisië", "ID": "Indonesië", "TH": "Thailand",
    "VN": "Vietnam", "PH": "Filipijnen", "CN": "China", "HK": "Hongkong", "TW": "Taiwan", "KR": "Zuid-Korea", "JP": "Japan",
    "AU": "Australië", "NZ": "Nieuw-Zeeland", "RU": "Rusland", "FI": "Finland", "EE": "Estland", "LT": "Litouwen",
    "LV": "Letland", "IL": "Israël", "TN": "Tunesië", "DZ": "Algerije", "SR": "Suriname", "VE": "Venezuela",
}  # fmt: skip

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


def port_index():
    """{"names": {naam: [codes]}, "codes": {code: naam}} uit Stamgegevens > Havens (kort in het geheugen)."""
    if _cache["index"] is not None and time.monotonic() - _cache["at"] < CACHE_SECONDS:
        return _cache["index"]
    from .models import Port, Terminal

    from django.db import DatabaseError, transaction

    names, codes, terminals = {}, {}, {}
    try:
        with transaction.atomic():  # tijdens oudere migraties bestaat de terminaltabel nog niet
            rows = list(Terminal.objects.filter(active=True).values_list("name", "aliases"))
    except DatabaseError:
        rows = []
    for name, aliases in rows:
        for alias in [name, *aliases.split(",")]:
            if _key(alias):
                terminals[_key(alias)] = name
    for locode, name, aliases in Port.objects.filter(active=True).values_list("locode", "name", "aliases"):
        codes[locode] = name
        for alias in [name, *aliases.split(",")]:
            if _key(alias):
                names.setdefault(_key(alias), [])
                if locode not in names[_key(alias)]:
                    names[_key(alias)].append(locode)
    _cache.update(at=time.monotonic(), index={"names": names, "codes": codes, "terminals": terminals})
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
    if len(candidates) == 1 or (candidates and country):
        return candidates[0]
    # Een onbekende code met spatie of cijfer ("NL RTM", "DE2XX") is duidelijk een code.
    if LOCODE_RE.fullmatch(compact) and (" " in raw or any(ch.isdigit() for ch in compact)):
        return compact
    return raw


def terminal_name(value):
    """"ECT EUROMAX ROTTERDAM" -> "ECT Euromax Terminal" als de terminal bekend is, anders ongewijzigd."""
    raw = (value or "").strip()
    return port_index()["terminals"].get(_key(raw), raw) if raw else ""


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


def recode_shipments():
    """Open dossiers met een havennaam i.p.v. code alsnog omzetten (bijv. nadat een haven is toegevoegd)."""
    from shipments.models import SeaShipment

    for pk, value in SeaShipment.objects.filter(status__in=SeaShipment.OPEN_STATUSES).exclude(terminal="").values_list("pk", "terminal"):
        name = terminal_name(value)
        if name != value:
            SeaShipment.objects.filter(pk=pk).update(terminal=name)

    for field in ("port_of_loading", "port_of_discharge"):
        rows = (SeaShipment.objects.filter(status__in=SeaShipment.OPEN_STATUSES).exclude(**{f"{field}__regex": r"^[A-Z]{2}[A-Z0-9]{3}$"})
                .exclude(**{field: ""}).values_list("pk", field))
        for pk, value in rows:
            code = port_code(value)
            if code != value:
                SeaShipment.objects.filter(pk=pk).update(**{field: code})
