import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from . import TrackingError, TrackingPending, get_provider
from ..models import SeaShipment, TrackingUpdate

log = logging.getLogger(__name__)
ETA_CHANGE_THRESHOLD = timedelta(hours=1)


def _json_safe(value):
    import json

    from django.core.serializers.json import DjangoJSONEncoder

    try:
        return json.loads(json.dumps(value, cls=DjangoJSONEncoder))
    except (TypeError, ValueError):
        return None


@transaction.atomic
def refresh_shipment(shipment: SeaShipment) -> TrackingUpdate | None:
    provider = get_provider(shipment.shipping_line)
    now = timezone.now()
    if provider is None:
        return None
    try:
        result = provider.track(shipment)
    except TrackingPending as exc:
        shipment.tracking_last_checked = now
        shipment.tracking_last_error = ""
        shipment.save(update_fields=["tracking_last_checked", "tracking_last_error"])
        return TrackingUpdate.objects.create(shipment=shipment, checked_at=now, provider=provider.name, message=str(exc)[:300])
    except TrackingError as exc:
        shipment.tracking_last_checked = now
        shipment.tracking_last_error = str(exc)[:300]
        shipment.save(update_fields=["tracking_last_checked", "tracking_last_error"])
        return TrackingUpdate.objects.create(
            shipment=shipment, checked_at=now, provider=provider.name, success=False, message=str(exc)[:300]
        )

    return apply_result(shipment, result, now)


def _vessel_tokens(name):
    import re

    return set(re.sub(r"[^A-Z0-9 ]", " ", (name or "").upper()).split()) - {"MV", "M/V", "MS"}


def same_vessel(name_a, name_b, imo_a="", imo_b=""):
    """Zelfde schip? IMO is leidend; anders namen vergelijken ("COSCO GEMINI" = "COSCO SHIPPING GEMINI")."""
    if imo_a and imo_b:
        return str(imo_a) == str(imo_b)
    a, b = _vessel_tokens(name_a), _vessel_tokens(name_b)
    if not a or not b:
        return True
    return a <= b or b <= a


def apply_result(shipment, result, now=None, provider_name=None):
    """Verwerk een trackingresultaat (van een API of handmatig geplakt) in het dossier."""
    now = now or timezone.now()
    messages = []
    old_eta = shipment.eta
    eta_changed = False
    vessel_changed = False

    if result.eta and (shipment.eta is None or abs(result.eta - shipment.eta) >= ETA_CHANGE_THRESHOLD):
        if shipment.eta:
            eta_changed = True
            messages.append(
                f"ETA gewijzigd van {timezone.localtime(shipment.eta):%d-%m %H:%M} naar {timezone.localtime(result.eta):%d-%m %H:%M}"
            )
        shipment.eta = result.eta

    new_vessel = (result.vessel_name or "").strip()
    if new_vessel:
        if shipment.vessel_name and not same_vessel(shipment.vessel_name, new_vessel, shipment.vessel_imo, result.vessel_imo):
            vessel_changed = True
            messages.append(f"Container verwisseld van schip: {shipment.vessel_name} → {new_vessel}")
            shipment.vessel_changed = True
            shipment.vessel_changed_at = now
        shipment.vessel_name = new_vessel
        # Bij een ander schip hoort het oude IMO-nummer er niet meer bij.
        shipment.vessel_imo = result.vessel_imo or ("" if vessel_changed else shipment.vessel_imo)
        shipment.voyage = result.voyage or shipment.voyage

    if result.ata and not shipment.ata:
        shipment.ata = result.ata
        messages.append(f"Aangekomen op {timezone.localtime(result.ata):%d-%m %H:%M}")
        if shipment.status == "verwacht":
            shipment.status = "aangekomen"

    for field in ("port_of_loading", "terminal"):
        value = getattr(result, field, "")
        if value and not getattr(shipment, field):
            setattr(shipment, field, value)
    if result.port_of_discharge:
        from core.ports import port_code

        pod = port_code(result.port_of_discharge)
        if pod and pod != shipment.port_of_discharge:
            messages.append(f"Loshaven: {pod}")
            shipment.port_of_discharge = pod
    if result.gate_out_at and shipment.status in SeaShipment.OPEN_STATUSES:
        # De container is bij de terminal opgehaald: uitgeleverd.
        shipment.status = "uitgeleverd"
        messages.append(f"Container opgehaald (gate out) op {timezone.localtime(result.gate_out_at):%d-%m %H:%M}")

    if result.eta_original:
        # De eerste ETA van de rederij is leidend voor de berekende vertraging.
        shipment.eta_original = result.eta_original
    if result.departed_at and not shipment.departed_at:
        shipment.departed_at = result.departed_at
    if result.discharged_at and not shipment.discharged_at:
        shipment.discharged_at = result.discharged_at
    if result.last_free_day and result.last_free_day != shipment.free_time_until:
        if shipment.free_time_until:
            messages.append(f"Vrije dagen gewijzigd: t/m {result.last_free_day:%d-%m}")
        shipment.free_time_until = result.last_free_day

    if len(result.vessels) > 1:
        messages.append("Overslag via: " + " → ".join(result.vessels))

    shipment.tracking_last_checked = now
    shipment.tracking_last_error = ""
    shipment.save()

    update = TrackingUpdate.objects.create(
        shipment=shipment,
        checked_at=now,
        provider=provider_name or result.provider,
        eta=result.eta,
        ata=result.ata,
        vessel_name=new_vessel,
        vessel_imo=result.vessel_imo,
        voyage=result.voyage,
        eta_changed=eta_changed,
        vessel_changed=vessel_changed,
        message="; ".join(messages)[:300],
        raw=_json_safe(result.raw),
    )

    from core import notifications

    if vessel_changed:
        notifications.vessel_changed(shipment, update)
    elif eta_changed:
        notifications.eta_changed(shipment, update, old_eta)

    if vessel_changed:
        from actions.models import Action

        action = Action(
            title=f"Schipwissel {shipment.container_number}: nu op {new_vessel}",
            description=update.message,
            priority=3,
            customer=shipment.customer,
            sea_shipment=shipment,
            owner=shipment.handler,
            due_date=timezone.localdate(),
        )
        action._skip_notify = True  # de behandelaar krijgt al de schipwissel-mail
        action.save()
    return update


def refresh_all(queryset=None, stale_after=timedelta(hours=0)):
    queryset = queryset if queryset is not None else SeaShipment.objects.filter(
        tracking_enabled=True, status__in=SeaShipment.OPEN_STATUSES, ata__isnull=True
    )
    cutoff = timezone.now() - stale_after
    updates = []
    from django.conf import settings

    from . import PROVIDERS

    now = timezone.now()
    for shipment in queryset.select_related("shipping_line", "customer", "handler"):
        if stale_after and shipment.tracking_last_checked and shipment.tracking_last_checked > cutoff:
            continue
        # Sommige bronnen verversen zelf maar elke paar uur; vaker vragen kost alleen tegoed.
        key = (shipment.shipping_line.tracking_provider if shipment.shipping_line else "") or settings.TRACKING_DEFAULT_PROVIDER
        min_hours = getattr(PROVIDERS.get(key), "min_interval_hours", 0)
        if min_hours and shipment.tracking_last_checked and now - shipment.tracking_last_checked < timedelta(hours=min_hours):
            continue
        try:
            update = refresh_shipment(shipment)
        except Exception:  # noqa: BLE001 - één kapotte container mag de rest niet blokkeren
            log.exception("Tracking mislukt voor %s", shipment)
            continue
        if update:
            updates.append(update)
    return updates
