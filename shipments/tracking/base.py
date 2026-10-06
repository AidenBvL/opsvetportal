from dataclasses import dataclass, field
from datetime import date, datetime


class TrackingError(Exception):
    pass


@dataclass
class Leg:
    vessel_name: str = ""
    vessel_imo: str = ""
    voyage: str = ""
    location: str = ""
    arrival: datetime | None = None
    arrival_classifier: str = ""  # PLN / EST / ACT


@dataclass
class TrackingResult:
    provider: str
    eta: datetime | None = None
    ata: datetime | None = None
    vessel_name: str = ""
    vessel_imo: str = ""
    voyage: str = ""
    legs: list[Leg] = field(default_factory=list)
    raw: object = None
    # Optioneel, alleen als de bron het levert:
    eta_original: datetime | None = None  # eerste ETA volgens de rederij
    discharged_at: datetime | None = None
    last_free_day: date | None = None  # laatste vrije dag (demurrage)
    port_of_loading: str = ""
    port_of_discharge: str = ""
    gate_out_at: datetime | None = None  # container opgehaald door/naar de ontvanger
    departed_at: datetime | None = None
    terminal: str = ""

    @property
    def vessels(self):
        seen = []
        for leg in self.legs:
            if leg.vessel_name and leg.vessel_name not in seen:
                seen.append(leg.vessel_name)
        return seen


class BaseProvider:
    name = "base"

    def __init__(self, shipping_line=None):
        self.shipping_line = shipping_line

    def track(self, shipment) -> TrackingResult:  # pragma: no cover - interface
        raise NotImplementedError
