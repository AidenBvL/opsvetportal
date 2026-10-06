"""Wijzigingslog via signals. De ingelogde gebruiker komt uit `CurrentUserMiddleware`."""

import contextvars
import datetime
import decimal

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, post_save, pre_save

_current_user = contextvars.ContextVar("current_user", default=None)
IGNORED_FIELDS = {"created_at", "updated_at", "tracking_last_checked", "calendar_token", "password", "last_login"}


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        token = _current_user.set(user if user is not None and user.is_authenticated else None)
        try:
            return self.get_response(request)
        finally:
            _current_user.reset(token)


def current_user():
    return _current_user.get()


def _display(instance, field):
    if field.is_relation:
        related = getattr(instance, field.name, None)
        return str(related) if related is not None else None
    if field.choices:
        value = getattr(instance, field.attname)
        return str(dict(field.flatchoices).get(value, value)) if value not in (None, "") else None
    value = getattr(instance, field.attname)
    if isinstance(value, (set, frozenset)):
        from .fields import weekdays_label

        return weekdays_label(value)
    if isinstance(value, datetime.datetime):
        from django.utils import timezone

        return timezone.localtime(value).strftime("%d-%m-%Y %H:%M") if timezone.is_aware(value) else value.strftime("%d-%m-%Y %H:%M")
    if isinstance(value, datetime.date):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, bool):
        return "ja" if value else "nee"
    if value in (None, ""):
        return None
    return str(value)[:200]


def _snapshot(instance):
    return {
        f.name: (_raw(instance, f), f)
        for f in instance._meta.concrete_fields
        if f.name not in IGNORED_FIELDS and not f.primary_key
    }


def _raw(instance, field):
    value = getattr(instance, field.attname)
    return sorted(value) if isinstance(value, (set, frozenset)) else value


def log_event(obj, message, user=None, action="event", changes=None):
    from .models import AuditLog

    return AuditLog.objects.create(
        user=user or current_user(),
        action=action,
        content_type=ContentType.objects.get_for_model(obj) if obj is not None else None,
        object_id=str(obj.pk) if obj is not None else "",
        object_repr=str(obj)[:250] if obj is not None else message[:250],
        changes=changes or {},
        message=message[:300],
    )


def _pre_save(sender, instance, **kwargs):
    instance._audit_old = None
    if instance.pk:
        old = sender._default_manager.filter(pk=instance.pk).first()
        if old is not None:
            instance._audit_old = {name: (value, _display(old, f)) for name, (value, f) in _snapshot(old).items()}


def _post_save(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    if created:
        log_event(instance, "", action="create")
        return
    old = getattr(instance, "_audit_old", None) or {}
    changes = {}
    for name, (value, field) in _snapshot(instance).items():
        if name in old and old[name][0] != value:
            changes[str(field.verbose_name)] = [old[name][1], _display(instance, field)]
    if changes:
        log_event(instance, "", action="update", changes=changes)


def _post_delete(sender, instance, **kwargs):
    log_event(instance, "", action="delete")


def register(*models):
    for model in models:
        uid = f"audit-{model._meta.label_lower}"
        pre_save.connect(_pre_save, sender=model, dispatch_uid=uid + "-pre")
        post_save.connect(_post_save, sender=model, dispatch_uid=uid + "-post")
        post_delete.connect(_post_delete, sender=model, dispatch_uid=uid + "-del")


def history_for(obj, limit=50):
    from .models import AuditLog

    return AuditLog.objects.filter(
        content_type=ContentType.objects.get_for_model(obj), object_id=str(obj.pk)
    ).select_related("user")[:limit]
