"""Kolommen van de zeevrachtlijst. Iedere gebruiker kiest zelf welke zichtbaar zijn en in welke volgorde.

Een kolom heeft een sleutel (gebruikt in shipments/_sea_cell.html), een titel, een groep voor het
kolommenmenu, en hoe er gesorteerd wordt ("" = tekst, "num", "date").
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    group: str
    sort: str = ""
    help: str = ""
    locked: bool = False  # altijd zichtbaar (de container zelf)


SEA_COLUMNS = [
    Column("container", "Container", "Container", locked=True, help="Containernummer en type"),
    Column("attention", "Aandacht", "Slim", "num", "Wat vandaag actie vraagt: CHED, transport plannen, vrije dagen, schipwissel"),
    Column("customer", "Klant / referentie", "Container", help="Klant met klant- en Cory-referentie"),
    Column("bl", "B/L / booking", "Container"),
    Column("seal", "Zegel", "Container"),
    Column("shipping_line", "Rederij", "Reis"),
    Column("vessel", "Schip / reis", "Reis", help="Inclusief schipwissel"),
    Column("route", "Route", "Reis", help="Laadhaven → loshaven"),
    Column("terminal", "Terminal", "Reis"),
    Column("departed", "Vertrokken", "Reis", "date"),
    Column("eta", "ETA / ATA", "Reis", "date", "Met aantal dagen en vertraging"),
    Column("discharged", "Gelost", "Reis", "date"),
    Column("free_days", "Vrije dagen", "Reis", "num", "Dagen tot einde vrije dagen (demurrage)"),
    Column("road_loading", "Ophalen (transport)", "Wegtransport", "date", "Datum en adres waar de vervoerder laadt"),
    Column("road_unloading", "Lossen (transport)", "Wegtransport", "date", "Leverdatum en losadres bij de klant"),
    Column("road_carrier", "Vervoerder", "Wegtransport", help="Vervoerder, chauffeur en transportstatus"),
    Column("empty_return", "Lege retour", "Wegtransport", "date", "Depot en uiterste datum"),
    Column("inspection_point", "Keurpunt", "Keuring & douane"),
    Column("inspection", "Keuring / CHED", "Keuring & douane"),
    Column("inspection_planned", "Keuring gepland", "Keuring & douane", "date"),
    Column("customs", "Douane", "Keuring & douane"),
    Column("goods", "Goederen", "Lading"),
    Column("temperature", "Temp.", "Lading", "num"),
    Column("cargo", "Gewicht / colli", "Lading", "num"),
    Column("documents", "Documenten", "Werk", "num"),
    Column("actions", "Open acties", "Werk", "num"),
    Column("handler", "Behandelaar", "Werk"),
    Column("tracking", "Tracking", "Werk", "date", "Laatst gecontroleerd en eventuele fout"),
    Column("status", "Status", "Werk"),
]
COLUMNS_BY_KEY = {c.key: c for c in SEA_COLUMNS}

# Kant-en-klare indelingen in het kolommenmenu.
PRESETS = {
    "standaard": ("Standaard", ["container", "attention", "customer", "vessel", "eta", "road_loading", "road_unloading",
                                 "inspection", "free_days", "status"]),
    "planning": ("Transportplanning", ["container", "attention", "customer", "terminal", "eta", "discharged", "road_loading",
                                       "road_unloading", "road_carrier", "free_days", "empty_return", "status"]),
    "keuring": ("Keuring & douane", ["container", "attention", "customer", "goods", "temperature", "eta", "inspection_point",
                                     "inspection", "inspection_planned", "customs", "documents", "status"]),
    "alles": ("Alles", [c.key for c in SEA_COLUMNS]),
}
DEFAULT_COLUMNS = PRESETS["standaard"][1]
PREFERENCE_KEY = "zeevracht"


def clean_columns(keys):
    """Alleen bestaande kolommen, geen dubbele, en de container altijd vooraan."""
    seen, result = set(), []
    for key in keys or []:
        if key in COLUMNS_BY_KEY and key not in seen:
            seen.add(key)
            result.append(key)
    for column in SEA_COLUMNS:
        if column.locked and column.key not in seen:
            result.insert(0, column.key)
    return result or list(DEFAULT_COLUMNS)


def user_columns(user):
    from core.models import ListPreference

    pref = ListPreference.objects.filter(user=user, key=PREFERENCE_KEY).first()
    keys = clean_columns(pref.columns) if pref and pref.columns else list(DEFAULT_COLUMNS)
    return [COLUMNS_BY_KEY[k] for k in keys], bool(pref and pref.compact)
