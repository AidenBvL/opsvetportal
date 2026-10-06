"""E-mailnotificaties. Alle mails worden pas verstuurd na een geslaagde database-transactie."""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import NotificationPreference

log = logging.getLogger(__name__)


def absolute(path):
    return settings.PORTAL_BASE_URL + path


def _recipients(users, flag, exclude=None):
    result = []
    for user in users:
        if not user or not user.is_active or not user.email or (exclude is not None and user == exclude):
            continue
        if getattr(NotificationPreference.for_user(user), flag):
            result.append(user)
    return result


def send(users, subject, template, context):
    """Verstuur per gebruiker een tekstmail (na commit)."""
    users = list({u.pk: u for u in users}.values())
    if not users:
        return 0

    def _send():
        for user in users:
            body = render_to_string(f"emails/{template}.txt", {**context, "user": user, "base_url": settings.PORTAL_BASE_URL})
            try:
                send_mail(f"[OPS/VET] {subject}", body, settings.DEFAULT_FROM_EMAIL, [user.email])
            except Exception:  # noqa: BLE001 - een mailfout mag het portaal niet blokkeren
                log.exception("Mail naar %s mislukt", user.email)

    transaction.on_commit(_send)
    return len(users)


def shipment_watchers(shipment, flag):
    handler_user = getattr(shipment.handler, "user", None) if shipment.handler_id else None
    users = []
    for prefs in NotificationPreference.objects.filter(**{flag: True}).select_related("user"):
        if prefs.shipment_scope == "all" or prefs.user == handler_user:
            users.append(prefs.user)
    if handler_user and not NotificationPreference.objects.filter(user=handler_user).exists():
        users.append(handler_user)  # standaardvoorkeuren gelden ook zonder opgeslagen voorkeur
    return [u for u in _recipients(users, flag) if not hasattr(u, "profile") or u.profile.customer_id is None]


# --- Gebeurtenissen ----------------------------------------------------------


def vessel_changed(shipment, update):
    users = shipment_watchers(shipment, "vessel_change")
    return send(users, f"Schipwissel {shipment.container_number} ({shipment.customer})", "vessel_change",
                {"shipment": shipment, "update": update, "url": absolute(reverse("shipments:sea_detail", args=[shipment.pk]))})


def eta_changed(shipment, update, old_eta):
    hours = abs((shipment.eta - old_eta).total_seconds()) / 3600 if old_eta and shipment.eta else 0
    users = [u for u in shipment_watchers(shipment, "eta_change") if hours >= NotificationPreference.for_user(u).eta_threshold_hours]
    return send(users, f"ETA {shipment.container_number} verschoven ({hours:+.0f} uur)" if shipment.eta > old_eta else
                f"ETA {shipment.container_number} vervroegd ({hours:.0f} uur)", "eta_change",
                {"shipment": shipment, "old_eta": old_eta, "hours": round(hours),
                 "url": absolute(reverse("shipments:sea_detail", args=[shipment.pk]))})


def action_assigned(action):
    user = getattr(action.owner, "user", None) if action.owner_id else None
    from .audit import current_user

    users = _recipients([user], "action_assigned", exclude=current_user())
    return send(users, f"{action.get_kind_display()} voor jou: {action.title}", "action_assigned",
                {"action": action, "url": absolute(reverse("actions:action_detail", args=[action.pk]))})


def escalation_raised(action):
    from .audit import current_user

    users = _recipients([p.user for p in NotificationPreference.objects.filter(escalations=True).select_related("user")],
                        "escalations", exclude=current_user())
    return send(users, f"Escalatie niveau {action.escalation_level}: {action.title}", "escalation",
                {"action": action, "url": absolute(reverse("actions:action_detail", args=[action.pk]))})


def swap_event(request_obj, users, subject):
    users = _recipients(users, "swap_requests")
    return send(users, subject, "swap_request", {"swap": request_obj, "url": absolute(reverse("planning:swap_list"))})


# --- Dagelijkse mails ---------------------------------------------------------


def daily_digest(today=None):
    from actions.models import Action
    from meetings.models import MeetingItem
    from shipments.models import SeaShipment

    today = today or timezone.localdate()
    sent = 0
    for prefs in NotificationPreference.objects.filter(daily_digest=True, user__is_active=True).select_related("user"):
        user = prefs.user
        if not user.email or (hasattr(user, "profile") and user.profile.customer_id):
            continue
        employee = getattr(user, "employee", None)
        open_actions = Action.objects.filter(status__in=Action.OPEN_STATUSES)
        mine = open_actions.filter(owner=employee) if employee else open_actions.none()
        arrivals = SeaShipment.objects.filter(status__in=SeaShipment.OPEN_STATUSES, eta__date__range=(today, today + timedelta(days=1)))
        if prefs.shipment_scope == "mine":
            arrivals = arrivals.filter(handler=employee) if employee else arrivals.none()
        context = {
            "today": today,
            "overdue": mine.filter(due_date__lt=today),
            "due_today": mine.filter(due_date=today),
            "escalations": open_actions.filter(kind=Action.KIND_ESCALATION) if prefs.escalations else [],
            "arrivals": arrivals.select_related("customer", "inspection_point"),
            "questions": MeetingItem.objects.filter(status="open", colleagues=employee).select_related("meeting") if employee else [],
            "url": absolute("/"),
        }
        if any(len(context[k]) for k in ("overdue", "due_today", "escalations", "arrivals", "questions")):
            sent += send([user], f"Dagoverzicht {today:%d-%m-%Y}", "daily_digest", context)
    return sent


def shift_reminders(today=None):
    from planning.models import Shift

    tomorrow = (today or timezone.localdate()) + timedelta(days=1)
    sent = 0
    for shift in Shift.objects.filter(date=tomorrow).select_related("employee__user"):
        users = _recipients([getattr(shift.employee, "user", None)], "shift_reminder")
        sent += send(users, f"Morgen {shift.get_shift_type_display().lower()}", "shift_reminder",
                     {"shift": shift, "url": absolute(reverse("planning:calendar"))})
    return sent


def send_invite(user, subject="Je account voor het portaal van Cory Brothers"):
    """Stuur een link waarmee de gebruiker zelf een wachtwoord instelt (geen wachtwoord per mail)."""
    from urllib.parse import urlparse

    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    parsed = urlparse(settings.PORTAL_BASE_URL)
    context = {
        "user": user, "protocol": parsed.scheme, "domain": parsed.netloc,
        "uid": urlsafe_base64_encode(force_bytes(user.pk)), "token": default_token_generator.make_token(user),
    }
    body = render_to_string("registration/password_reset_email.txt", context)

    def _send():
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
        except Exception:  # noqa: BLE001 - een mailfout mag het aanmaken van een account niet blokkeren
            log.exception("Uitnodiging naar %s mislukt", user.email)

    transaction.on_commit(_send)
