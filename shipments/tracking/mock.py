"""Demo-provider: genereert voorspelbare, licht wisselende ETA's en af en toe een schipwissel.

Handig om het portaal te testen zonder API-sleutels. Zet per rederij een echte
provider (bijv. DCSA) zodra de API-toegang geregeld is.
"""

import hashlib
from datetime import datetime, time, timedelta

from django.utils import timezone

from .base import BaseProvider, Leg, TrackingResult

VESSELS = [
    ("MAERSK HIDALGO", "9786786"),
    ("MSC GÜLSÜN", "9839430"),
    ("CMA CGM JACQUES SAADE", "9839131"),
    ("HAPAG BERLIN EXPRESS", "9501356"),
    ("ONE INNOVATION", "9937183"),
    ("EVER ACE", "9893890"),
]


def _h(*parts):
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest(), 16)


class MockProvider(BaseProvider):
    name = "mock"

    def track(self, shipment):
        today = timezone.localdate()
        base_vessel = VESSELS[_h(shipment.container_number) % len(VESSELS)]
        if shipment.vessel_name:
            known = {name: imo for name, imo in VESSELS}
            base_vessel = (shipment.vessel_name, shipment.vessel_imo or known.get(shipment.vessel_name, ""))
        vessel = base_vessel
        # Ongeveer 1 op de 15 controles meldt een schipwissel (roll-over).
        if _h(shipment.container_number, today.isoformat(), "swap") % 15 == 0:
            others = [v for v in VESSELS if v[0] != base_vessel[0]]
            vessel = others[_h(shipment.container_number) % len(others)]
        anchor = shipment.eta_original or shipment.eta
        if anchor is None:
            start = timezone.localtime(shipment.created_at) if shipment.created_at else timezone.now()
            anchor = timezone.make_aware(
                datetime.combine(start.date() + timedelta(days=5 + _h(shipment.container_number) % 20), time(6)),
                timezone.get_current_timezone(),
            )
        drift_hours = (_h(shipment.container_number, today.isoformat()) % 49) - 12
        eta = anchor + timedelta(hours=drift_hours)
        ata = eta if eta < timezone.now() - timedelta(hours=6) else None
        voyage = f"{_h(shipment.container_number) % 900 + 100}W"
        leg = Leg(
            vessel_name=vessel[0],
            vessel_imo=vessel[1],
            voyage=voyage,
            location=shipment.port_of_discharge,
            arrival=eta,
            arrival_classifier="ACT" if ata else "EST",
        )
        return TrackingResult(
            provider=self.name,
            eta=eta,
            ata=ata,
            vessel_name=vessel[0],
            vessel_imo=vessel[1],
            voyage=voyage,
            legs=[leg],
            departed_at=anchor - timedelta(days=24),
            raw={"demo": True, "eta": eta.isoformat(), "vessel": vessel[0]},
        )
