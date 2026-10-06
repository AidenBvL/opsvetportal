"""Provider voor de DCSA Track & Trace standaard (o.a. Maersk, Hapag-Lloyd, CMA CGM, ONE, Evergreen, ZIM).

Ondersteunt TNT v2.2 (velden direct op het event) en v3 (velden onder `transportEvent`).
Configuratie per rederij: `api_base_url`, `api_key_env` (naam van de environment
variable met de sleutel) en `api_key_header`.
"""

import os
from datetime import datetime, timezone

import requests
from django.conf import settings

from .base import BaseProvider, Leg, TrackingError, TrackingResult

CLASSIFIER_RANK = {"PLN": 0, "EST": 1, "ACT": 2}


def _parse_dt(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _get(event, *keys):
    """Zoek een veld op het event zelf of in de v3 sub-objecten."""
    for container in (event, event.get("transportEvent") or {}, event.get("equipmentEvent") or {}):
        for key in keys:
            if container.get(key) not in (None, ""):
                return container[key]
    return None


def _location(call):
    loc = call.get("location") or {}
    return (call.get("UNLocationCode") or loc.get("UNLocationCode") or loc.get("locationName") or "").upper()


def parse_events(events, port_of_discharge=""):
    """Zet een lijst DCSA events om naar een TrackingResult."""
    pod = (port_of_discharge or "").upper()
    calls = {}
    for event in events or []:
        event_type = (_get(event, "eventType") or "").upper()
        if event_type and event_type != "TRANSPORT":
            continue
        code = (_get(event, "transportEventTypeCode") or "").upper()
        if code != "ARRI":
            continue
        call = event.get("transportCall") or _get(event, "transportCall") or {}
        vessel = call.get("vessel") or {}
        mode = (call.get("modeOfTransport") or "VESSEL").upper()
        if mode not in ("VESSEL", ""):
            continue
        location = _location(call)
        voyage = call.get("importVoyageNumber") or call.get("carrierImportVoyageNumber") or call.get("exportVoyageNumber") or call.get("carrierVoyageNumber") or ""
        key = (location, vessel.get("vesselIMONumber") or vessel.get("vesselName") or "", voyage)
        classifier = (_get(event, "eventClassifierCode") or "EST").upper()
        when = _parse_dt(_get(event, "eventDateTime"))
        created = _parse_dt(_get(event, "eventCreatedDateTime")) or when
        current = calls.get(key)
        rank = (CLASSIFIER_RANK.get(classifier, 1), created.timestamp() if created else 0)
        if current is None or rank >= current[0]:
            calls[key] = (
                rank,
                Leg(
                    vessel_name=(vessel.get("vesselName") or "").strip(),
                    vessel_imo=str(vessel.get("vesselIMONumber") or ""),
                    voyage=voyage,
                    location=location,
                    arrival=when,
                    arrival_classifier=classifier,
                ),
            )

    legs = sorted(
        (leg for _, leg in calls.values()),
        key=lambda leg: (leg.arrival is None, leg.arrival.timestamp() if leg.arrival else 0),
    )
    result = TrackingResult(provider="dcsa", legs=legs, raw=events)
    if not legs:
        return result
    final = [leg for leg in legs if pod and leg.location == pod] or [legs[-1]]
    final_leg = final[-1]
    result.vessel_name = final_leg.vessel_name
    result.vessel_imo = final_leg.vessel_imo
    result.voyage = final_leg.voyage
    if final_leg.arrival_classifier == "ACT":
        result.ata = final_leg.arrival
        result.eta = final_leg.arrival
    else:
        result.eta = final_leg.arrival
    return result


def oauth_token(line):
    """Haal (en cache) een OAuth2 access token op via client credentials."""
    from django.core.cache import cache

    cache_key = f"tracking-token-{line.pk}"
    token = cache.get(cache_key)
    if token:
        return token
    client_id = os.environ.get(line.oauth_client_id_env or "")
    secret = os.environ.get(line.oauth_client_secret_env or "")
    if not client_id or not secret:
        raise TrackingError("OAuth2 client-ID of -secret ontbreekt (controleer de omgevingsvariabelen).")
    try:
        response = requests.post(
            line.oauth_token_url,
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret},
            headers={"Accept": "application/json", **({line.api_key_header or "Consumer-Key": client_id} if line.api_key_header else {})},
            timeout=settings.TRACKING_HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise TrackingError(f"Token ophalen bij {line.name} mislukt: {exc}") from exc
    if response.status_code >= 400:
        raise TrackingError(f"Token ophalen mislukt ({response.status_code}): {response.text[:200]}")
    data = response.json()
    token = data["access_token"]
    cache.set(cache_key, token, max(int(data.get("expires_in", 3600)) - 60, 60))
    return token


class DCSAProvider(BaseProvider):
    name = "dcsa"

    def track(self, shipment):
        line = self.shipping_line
        if not line or not line.api_base_url:
            raise TrackingError("Geen API base URL ingesteld voor deze rederij.")
        headers = {"Accept": "application/json", "API-Version": "2"}
        if line.api_key_env:
            key = os.environ.get(line.api_key_env)
            if not key:
                raise TrackingError(f"Omgevingsvariabele {line.api_key_env} met de API-sleutel is niet gezet.")
            headers[line.api_key_header or "Consumer-Key"] = key
        if line.oauth_token_url:
            headers["Authorization"] = f"Bearer {oauth_token(line)}"
        params = {"equipmentReference": shipment.container_number, "eventType": "TRANSPORT"}
        if shipment.bl_number:
            params["transportDocumentReference"] = shipment.bl_number
        url = line.api_base_url.rstrip("/") + "/events"
        try:
            response = requests.get(url, headers=headers, params=params, timeout=settings.TRACKING_HTTP_TIMEOUT)
        except requests.RequestException as exc:
            raise TrackingError(f"Verbinding met {line.name} mislukt: {exc}") from exc
        if response.status_code == 404:
            raise TrackingError("Container niet gevonden bij de rederij.")
        if response.status_code >= 400:
            raise TrackingError(f"API-fout {response.status_code}: {response.text[:200]}")
        data = response.json()
        events = data.get("events", data) if isinstance(data, dict) else data
        return parse_events(events, shipment.port_of_discharge)
