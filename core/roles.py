"""Standaardrollen. Pas rechten daarna gerust aan via Beheer > Accounts & rechten."""

from django.contrib.auth.models import Group, Permission

from .forms import PORTAL_APPS

ROLES = {
    "Beheerder": {"apps": PORTAL_APPS, "actions": None},
    "Planner": {"apps": [a for a in PORTAL_APPS if a != "auth"], "actions": None,
                "exclude_models": [], "extra": ["planning.generate_roster", "shipments.refresh_tracking"]},
    "Operations": {"apps": ["core", "planning", "meetings", "actions", "shipments", "documents"],
                   "actions": ["view", "add", "change"], "readonly_models": ["employee", "department", "holiday", "rostermonth", "shift", "workfromhomeday"],
                   "extra": ["shipments.refresh_tracking", "meetings.delete_meetingitem"]},
    "Alleen lezen": {"apps": ["core", "planning", "meetings", "actions", "shipments", "documents"], "actions": ["view"]},
}


SYSTEM_MODELS = {"auditlog", "jobrun", "notificationpreference", "userprofile", "listpreference"}


def setup_roles():
    for name, spec in ROLES.items():
        group, _ = Group.objects.get_or_create(name=name)
        perms = Permission.objects.filter(content_type__app_label__in=spec["apps"])
        if spec.get("actions"):
            allowed = []
            for perm in perms:
                action = perm.codename.split("_", 1)[0]
                model = perm.content_type.model
                if model in spec.get("readonly_models", []):
                    if action == "view":
                        allowed.append(perm.pk)
                elif action in spec["actions"]:
                    allowed.append(perm.pk)
            perms = Permission.objects.filter(pk__in=allowed)
        else:
            perms = perms.exclude(codename__in=["generate_roster", "refresh_tracking"]) if name != "Beheerder" else perms
        extra = []
        for full in spec.get("extra", []):
            app, codename = full.split(".")
            extra += list(Permission.objects.filter(content_type__app_label=app, codename=codename))
        # Logregels en technische tabellen zijn nooit handmatig te bewerken.
        perms = [p for p in perms if p.content_type.model not in SYSTEM_MODELS or p.codename.startswith("view_auditlog")]
        group.permissions.set(list(perms) + extra)
    return list(ROLES)
