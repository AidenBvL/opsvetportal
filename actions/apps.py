from django.apps import AppConfig


class ActionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "actions"
    verbose_name = "Acties & escalaties"

    def ready(self):
        from django.db.models.signals import post_save, pre_save

        from .models import Action

        pre_save.connect(_remember_old, sender=Action, dispatch_uid="action-notify-pre")
        post_save.connect(_notify, sender=Action, dispatch_uid="action-notify-post")


def _remember_old(sender, instance, **kwargs):
    old = sender.objects.filter(pk=instance.pk).values("owner_id", "escalation_level", "kind").first() if instance.pk else None
    instance._notify_old = old or {}


def _notify(sender, instance, created, raw=False, **kwargs):
    if raw or getattr(instance, "_skip_notify", False):
        return
    from core import notifications

    old = getattr(instance, "_notify_old", {}) or {}
    if instance.owner_id and instance.owner_id != old.get("owner_id"):
        notifications.action_assigned(instance)
    is_escalation = instance.kind == sender.KIND_ESCALATION
    level_up = (instance.escalation_level or 0) > (old.get("escalation_level") or 0) or old.get("kind") != instance.kind
    if is_escalation and instance.is_open and level_up:
        notifications.escalation_raised(instance)
