from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Stamgegevens"

    def ready(self):
        from django.apps import apps

        from . import audit

        audit.register(*[apps.get_model(label) for label in [
            "core.Customer", "core.ShippingLine", "core.RoadCarrier", "core.InspectionPoint",
            "planning.Employee", "planning.Absence", "planning.Shift", "planning.RosterMonth",
            "actions.Action", "actions.ExtraCost",
            "shipments.SeaShipment", "shipments.RoadTransport",
            "meetings.MeetingItem", "documents.Document", "auth.User",
        ]])
