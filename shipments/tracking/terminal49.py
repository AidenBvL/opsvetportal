"""Provider voor Terminal49 (één API voor bijna alle rederijen).

Werking: het portaal meldt een container (of B/L) aan via een tracking request. Terminal49
zoekt de zending op bij de rederij; daarna leest het portaal bij elke ronde de ETA, het
schip en de aankomst uit. De API-sleutel staat in de omgevingsvariabele TERMINAL49_API_KEY.
"""

from datetime import datetime, timezone

import requests
from django.conf import settings
from django.utils import timezone as dj_timezone

from .base import BaseProvider, Leg, TrackingError, TrackingResult

API = "https://api.terminal49.com/v2"


class TrackingPending(TrackingError):
    """De zending is aangemeld maar Terminal49 heeft nog geen gegevens."""


class DuplicateRequest(TrackingError):
    """Terminal49 kent deze zending al (aangemeld via het dashboard of een eerdere poging)."""


def _dt(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class Terminal49Provider(BaseProvider):
    name = "terminal49"

    def _headers(self):
        key = settings.TERMINAL49_API_KEY
        if not key:
            raise TrackingError("TERMINAL49_API_KEY is niet ingesteld.")
        return {"Authorization": f"Token {key}", "Content-Type": "application/vnd.api+json", "Accept": "application/json"}

    def _call(self, method, path, **kwargs):
        try:
            response = requests.request(method, API + path, headers=self._headers(), timeout=settings.TRACKING_HTTP_TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            raise TrackingError(f"Verbinding met Terminal49 mislukt: {exc}") from exc
        if response.status_code >= 400:
            errors = []
            try:
                errors = response.json().get("errors", []) or []
            except (ValueError, AttributeError):
                pass
            detail = "; ".join(e.get("detail") or e.get("title", "") for e in errors if isinstance(e, dict)) or response.text[:150]
            where = f"{method} {path.split('?')[0]}"
            if response.status_code == 401:
                raise TrackingError(f"Terminal49 401 bij {where}: API-sleutel ongeldig of verwijderd. "
                                    f"Controleer TERMINAL49_API_KEY in Render. ({detail})"[:300])
            if response.status_code == 403:
                raise TrackingError(f"Terminal49 403 bij {where}: geen toegang tot deze gegevens, "
                                    f"mogelijk niet in je abonnement. ({detail})"[:300])
            if response.status_code == 429:
                raise TrackingError("Terminal49: te veel verzoeken, volgende ronde opnieuw.")
            if response.status_code == 422 and any(e.get("code") == "duplicate" for e in errors):
                raise DuplicateRequest(detail[:300])
            raise TrackingError(f"Terminal49 fout {response.status_code}: {detail}"[:300])
        return response.json()

    def _scac(self, shipment):
        line = shipment.shipping_line or self.shipping_line
        if not line or not line.scac:
            raise TrackingError("Vul de SCAC-code van de rederij in (bijv. MAEU); Terminal49 heeft die nodig.")
        return line.scac.upper()

    def _request_number(self, shipment):
        """B/L is het betrouwbaarst, dan boeking; containernummer wordt niet door elke rederij ondersteund."""
        if shipment.bl_number:
            return "bill_of_lading", shipment.bl_number
        if shipment.booking_number:
            return "booking_number", shipment.booking_number
        return "container", shipment.container_number

    def _create_request(self, shipment):
        request_type, number = self._request_number(shipment)
        scac = self._scac(shipment)
        body = {"data": {"type": "tracking_request", "attributes": {
            "request_type": request_type, "request_number": number, "scac": scac,
        }}}
        try:
            data = self._call("POST", "/tracking_requests", json=body)["data"]
        except DuplicateRequest:
            data = self._find_existing(number, scac)
        shipment.external_tracking_id = f"tr:{data['id']}"
        shipment.save(update_fields=["external_tracking_id"])
        return data

    def _find_existing(self, number, scac):
        """Zoek de bestaande tracking request op, zodat het portaal die gewoon gaat volgen."""
        found = self._call("GET", "/tracking_requests", params={"q": number}).get("data", [])
        for item in found:
            attrs = item.get("attributes", {})
            if attrs.get("request_number", "").upper() == number.upper() and (attrs.get("scac") or "").upper() == scac:
                return item
        raise TrackingError(f"Terminal49 meldt dat {number} al gevolgd wordt, maar de aanvraag is niet terug te vinden.")

    def _shipment_id(self, shipment):
        ref = shipment.external_tracking_id or ""
        if ref.startswith("shp:"):
            return ref[4:]
        if ref.startswith("tr:"):
            data = self._call("GET", f"/tracking_requests/{ref[3:]}")["data"]
        else:
            data = self._create_request(shipment)
        attrs = data.get("attributes", {})
        if attrs.get("status") == "failed":
            shipment.external_tracking_id = ""
            shipment.save(update_fields=["external_tracking_id"])
            raise TrackingError(f"Terminal49 kon de zending niet vinden: {attrs.get('failed_reason') or 'onbekende reden'}")
        tracked = (data.get("relationships", {}).get("tracked_object") or {}).get("data")
        if not tracked:
            raise TrackingPending("Aangemeld bij Terminal49; de gegevens volgen meestal binnen een paar minuten.")
        shipment.external_tracking_id = f"shp:{tracked['id']}"
        shipment.save(update_fields=["external_tracking_id"])
        return tracked["id"]

    def track(self, shipment):
        shipment_id = self._shipment_id(shipment)
        payload = self._call("GET", f"/shipments/{shipment_id}", params={"include": "containers"})
        return parse_shipment(payload, shipment.container_number)


def parse_shipment(payload, container_number=""):
    attrs = payload.get("data", {}).get("attributes", {})
    container = next(
        (c.get("attributes", {}) for c in payload.get("included", [])
         if c.get("type") == "container" and c.get("attributes", {}).get("number") == container_number),
        {},
    )
    eta = _dt(attrs.get("pod_eta_at"))
    ata = _dt(attrs.get("pod_ata_at")) or _dt(container.get("pod_arrived_at"))
    leg = Leg(
        vessel_name=(attrs.get("pod_vessel_name") or "").strip(),
        vessel_imo=str(attrs.get("pod_vessel_imo") or ""),
        voyage=attrs.get("pod_voyage_number") or "",
        location=attrs.get("port_of_discharge_locode") or "",
        arrival=ata or eta,
        arrival_classifier="ACT" if ata else "EST",
    )
    lfd = _dt(container.get("pickup_lfd"))
    return TrackingResult(
        provider="terminal49",
        eta=ata or eta,
        ata=ata,
        eta_original=_dt(attrs.get("pod_original_eta_at")),
        discharged_at=_dt(container.get("pod_discharged_at")),
        last_free_day=dj_timezone.localtime(lfd).date() if lfd else None,
        vessel_name=leg.vessel_name,
        vessel_imo=leg.vessel_imo,
        voyage=leg.voyage,
        legs=[leg],
        raw={"shipment": attrs, "container": container},
    )
