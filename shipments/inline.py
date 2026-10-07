"""Direct bewerken in de zeevrachtlijst: één veld per keer, met dezelfde controles als het bewerkscherm."""

from django import forms
from django.db import models
from django.forms import modelform_factory
from django.utils import timezone

from .columns import SEA_COLUMNS
from .models import SeaShipment

EDITABLE_FIELDS = [c.edit for c in SEA_COLUMNS if c.edit]


def _choices_for(field):
    if field.choices:
        return [[str(value), str(label)] for value, label in field.choices]
    if isinstance(field, models.ForeignKey):
        from core.models import InspectionPoint
        from planning.models import Employee

        model = field.related_model
        qs = {Employee: Employee.objects.filter(active=True), InspectionPoint: InspectionPoint.objects.filter(active=True)}.get(model)
        return [[str(obj.pk), str(obj)] for obj in (qs if qs is not None else model.objects.all())]
    return None


def field_specs():
    """Per bewerkbaar veld: titel, soort invoer en keuzes. Gaat als JSON mee naar de pagina."""
    specs = {}
    for name in EDITABLE_FIELDS:
        field = SeaShipment._meta.get_field(name)
        if isinstance(field, models.BooleanField):
            kind = "bool"
        elif field.choices or isinstance(field, models.ForeignKey):
            kind = "select"
        elif isinstance(field, models.DateTimeField):
            kind = "datetime"
        elif isinstance(field, models.DateField):
            kind = "date"
        elif isinstance(field, models.DecimalField):
            kind = "number"
        else:
            kind = "text"
        specs[name] = {"label": str(field.verbose_name).capitalize(), "type": kind, "choices": _choices_for(field),
                       "nullable": field.null or field.blank}
    return specs


def edit_value(shipment, name):
    """De huidige waarde zoals het invoerveld hem verwacht (datum als JJJJ-MM-DD, keuze als sleutel, ...)."""
    field = SeaShipment._meta.get_field(name)
    value = getattr(shipment, field.attname)
    if value is None:
        return ""
    if isinstance(field, models.BooleanField):
        return "1" if value else "0"
    if isinstance(field, models.DateTimeField):
        return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")
    if isinstance(field, models.DateField):
        return value.isoformat()
    return str(value)


def apply_edit(shipment, name, raw):
    """Zet één veld. Geeft (gelukt, foutmelding) terug."""
    if name not in EDITABLE_FIELDS:
        return False, "Dit veld kan niet direct worden aangepast."
    field = SeaShipment._meta.get_field(name)
    data = {}
    if isinstance(field, models.BooleanField):
        if raw in ("1", "true", "on"):
            data[name] = "on"
    else:
        data[name] = raw
    widgets = {name: forms.DateTimeInput(format="%Y-%m-%dT%H:%M")} if isinstance(field, models.DateTimeField) else None
    form = modelform_factory(SeaShipment, fields=[name], widgets=widgets)(data, instance=shipment)
    if not form.is_valid():
        return False, "; ".join(str(e) for errors in form.errors.values() for e in errors)
    form.save()
    return True, ""
