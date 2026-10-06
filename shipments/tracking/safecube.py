"""Provider voor Safecube (Sinay) Container Tracking API.

GET {SAFECUBE_BASE_URL}/shipment?shipmentNumber=...&shipmentType=BL|BK|CT&sealine=SCAC
De API-sleutel gaat mee in de header SAFECUBE_API_KEY_HEADER (standaard "API_KEY").
Tracken per B/L is het voordeligst: één zending, ongeacht het aantal containers.
Safecube ververst de data elke 6-24 uur; vaker dan elke 6 uur opvragen heeft geen zin.
"""

from datetime import datetime, timezone

import requests
from django.conf import settings

from .base import BaseProvider, Leg, TrackingError, TrackingResult
from .terminal49 import TrackingPending


def _dt(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _error_text(data):
    if not isinstance(data, dict):
        return ""
    for key in ("message", "errorMessage", "description", "error", "errorCode", "code"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            return _error_text(value)
    return ""


class SafecubeProvider(BaseProvider):
    name = "safecube"
    min_interval_hours = 6

    def track(self, shipment):
        key = settings.SAFECUBE_API_KEY
        if not key:
            raise TrackingError("SAFECUBE_API_KEY is niet ingesteld.")
        if shipment.bl_number:
            number, kind = shipment.bl_number, "BL"
        elif shipment.booking_number:
            number, kind = shipment.booking_number, "BK"
        else:
            number, kind = shipment.container_number, "CT"
        params = {"shipmentNumber": number, "shipmentType": kind, "route": "false", "ais": "false"}
        line = shipment.shipping_line or self.shipping_line
        if line and line.scac:
            params["sealine"] = line.scac.upper()
        try:
            response = requests.get(
                settings.SAFECUBE_BASE_URL.rstrip("/") + "/shipment",
                params=params,
                headers={settings.SAFECUBE_API_KEY_HEADER: key, "Accept": "application/json"},
                timeout=max(settings.TRACKING_HTTP_TIMEOUT, 60),
            )
        except requests.Timeout as exc:
            raise TrackingPending("Safecube is de gegevens nog aan het ophalen; volgende ronde opnieuw.") from exc
        except requests.RequestException as exc:
            raise TrackingError(f"Verbinding met Safecube mislukt: {exc}") from exc

        try:
            data = response.json()
        except ValueError:
            data = {}
        detail = _error_text(data) or response.text[:150]
        if response.status_code == 504:
            raise TrackingPending("Safecube haalt de gegevens nog op bij de rederij; volgende ronde opnieuw.")
        if response.status_code in (401, 403):
            raise TrackingError(f"Safecube {response.status_code}: API-sleutel geweigerd of geen tegoed meer. ({detail})"[:300])
        if response.status_code == 402 or ("credit" in detail.lower() and response.status_code >= 400):
            raise TrackingError(f"Safecube: tegoed op of limiet bereikt. ({detail})"[:300])
        if response.status_code >= 400:
            raise TrackingError(f"Safecube fout {response.status_code}: {detail}"[:300])
        if not isinstance(data, dict) or "metadata" not in data:
            # Bijv. SEALINE_HASNT_PROVIDE_INFO: de rederij heeft (nog) niets; later opnieuw proberen.
            raise TrackingPending(f"Safecube heeft nog geen gegevens van de rederij ({detail or 'geen details'}).")
        return parse_shipment(data, shipment.container_number)


def parse_shipment(data, container_number=""):
    route = data.get("route") or {}
    pod = route.get("pod") or {}
    pol = route.get("pol") or {}
    pod_date = _dt(pod.get("date"))
    predictive = _dt(pod.get("predictiveEta"))
    actual = bool(pod.get("actual"))

    containers = data.get("containers") or []
    container = next((c for c in containers if (c.get("number") or "").upper() == container_number.upper()), None)
    if container is None and containers:
        container = containers[0]
    events = (container or {}).get("events") or []

    def last_event(status_codes, require_actual=None):
        found = None
        for event in events:
            if event.get("status") in status_codes and (require_actual is None or bool(event.get("isActual")) == require_actual):
                found = event
        return found

    arrival = last_event({"VAD"}) or next((e for e in reversed(events) if e.get("vessel")), None)
    vessel = (arrival or {}).get("vessel") or {}
    if not vessel and data.get("vessels"):
        vessel = data["vessels"][-1]
    discharge = last_event({"CDD"}, require_actual=True)
    facility = (arrival or {}).get("facility")
    terminal = facility.get("name", "") if isinstance(facility, dict) else (facility or "")

    ata = pod_date if actual else None
    eta = pod_date or predictive
    legs = []
    for event in events:
        if event.get("status") in {"VAD", "VAT"} and event.get("vessel"):
            legs.append(Leg(
                vessel_name=event["vessel"].get("name", ""),
                vessel_imo=str(event["vessel"].get("imo") or ""),
                voyage=event.get("voyage") or "",
                location=((event.get("location") or {}).get("locode") or ""),
                arrival=_dt(event.get("date")),
                arrival_classifier="ACT" if event.get("isActual") else "EST",
            ))
    pol_location = pol.get("location") or {}
    return TrackingResult(
        provider="safecube",
        eta=eta,
        ata=ata,
        vessel_name=(vessel.get("name") or "").strip(),
        vessel_imo=str(vessel.get("imo") or ""),
        voyage=(arrival or {}).get("voyage") or "",
        legs=legs,
        raw={"metadata": data.get("metadata"), "route": route},
        discharged_at=_dt(discharge.get("date")) if discharge else None,
        port_of_loading=pol_location.get("locode") or pol_location.get("name", ""),
        departed_at=_dt(pol.get("date")) if pol.get("actual") else None,
        terminal=terminal,
    )
