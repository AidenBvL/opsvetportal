"""Tracking providers voor ETA / zeeschip informatie.

Een provider implementeert `track(shipment) -> TrackingResult`. Nieuwe bronnen
(bijv. een aggregator als Portbase, Vizion, Terminal49 of ShipsGo) voeg je toe
door een klasse te schrijven en die te registreren in `PROVIDERS`.
"""

from .base import TrackingError, TrackingResult  # noqa: F401
from .dcsa import DCSAProvider
from .mock import MockProvider
from .terminal49 import Terminal49Provider, TrackingPending  # noqa: F401

PROVIDERS = {
    "mock": MockProvider,
    "dcsa": DCSAProvider,
    "terminal49": Terminal49Provider,
}


def get_provider(shipping_line):
    from django.conf import settings

    key = (shipping_line.tracking_provider if shipping_line else "") or settings.TRACKING_DEFAULT_PROVIDER
    if key == "none":
        return None
    try:
        return PROVIDERS[key](shipping_line)
    except KeyError as exc:
        raise TrackingError(f"Onbekende tracking provider '{key}'.") from exc
