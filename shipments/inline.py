"""Direct bewerken in de lijsten (zeevracht en wegtransport): één veld per keer, met dezelfde controles als het formulier."""

from django import forms
from django.db import models
from django.forms import modelform_factory
from django.utils import timezone

from .columns import SEA_COLUMNS
from .models import RoadTransport, SeaShipment

EDITABLE = {
    SeaShipment: [c.edit for c in SEA_COLUMNS if c.edit],
    RoadTransport: ["carrier", "loading_at", "loading_reference", "delivery_planned_at", "unloading_address",
                    "unloading_reference", "delivered_at", "cmr_number", "inspection_status", "status", "handler",
                    "empty_return_by"],
}
EDITABLE_FIELDS = EDITABLE[SeaShipment]  # voor bestaande aanroepen


def _queryset(model, name, related):
    from core.models import Address, InspectionPoint, RoadCarrier
    from planning.models import Employee

    if related is Address:
        qs = Address.objects.filter(active=True)
        if name == "unloading_address":
            qs = qs.exclude(kind="laad")
        elif name == "loading_address":
            qs = qs.exclude(kind="los")
        return qs.select_related("customer").order_by("name")
    filtered = {Employee, InspectionPoint, RoadCarrier}
    return related.objects.filter(active=True) if related in filtered else related.objects.all()


def _choices_for(model, field):
    if field.choices:
        return [[str(value), str(label)] for value, label in field.choices]
    if isinstance(field, models.ForeignKey):
        return [[str(obj.pk), str(obj)] for obj in _queryset(model, field.name, field.related_model)]
    return None


def field_specs(model=SeaShipment):
    """Per bewerkbaar veld: titel, soort invoer en keuzes. Gaat als JSON mee naar de pagina."""
    specs = {}
    for name in EDITABLE[model]:
        field = model._meta.get_field(name)
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
        specs[name] = {"label": str(field.verbose_name).capitalize(), "type": kind, "choices": _choices_for(model, field),
                       "nullable": field.null or field.blank}
    return specs


def edit_value(obj, name):
    """De huidige waarde zoals het invoerveld hem verwacht (datum als JJJJ-MM-DD, keuze als sleutel, ...)."""
    field = obj._meta.get_field(name)
    value = getattr(obj, field.attname)
    if value is None:
        return ""
    if isinstance(field, models.BooleanField):
        return "1" if value else "0"
    if isinstance(field, models.DateTimeField):
        return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")
    if isinstance(field, models.DateField):
        return value.isoformat()
    return str(value)


def apply_edit(obj, name, raw):
    """Zet één veld. Geeft (gelukt, foutmelding) terug."""
    model = type(obj)
    if name not in EDITABLE.get(model, []):
        return False, "Dit veld kan niet direct worden aangepast."
    field = model._meta.get_field(name)
    data = {}
    if isinstance(field, models.BooleanField):
        if raw in ("1", "true", "on"):
            data[name] = "on"
    else:
        data[name] = raw
    widgets = {name: forms.DateTimeInput(format="%Y-%m-%dT%H:%M")} if isinstance(field, models.DateTimeField) else None
    form = modelform_factory(model, fields=[name], widgets=widgets)(data, instance=obj)
    if isinstance(field, models.ForeignKey):
        form.fields[name].queryset = _queryset(model, name, field.related_model)
    if not form.is_valid():
        return False, "; ".join(str(e) for errors in form.errors.values() for e in errors)
    instance = form.save(commit=False)
    if name in ("loading_address", "unloading_address"):
        # Ander adres gekozen: het adresveld (en lege chauffeursinstructies) volgen het nieuwe adres.
        address = getattr(instance, name)
        place = name.replace("_address", "_place")
        setattr(instance, place, address.one_line[:250] if address else "")
        if address and name == "unloading_address" and not instance.driver_instructions:
            instance.driver_instructions = address.instructions
    instance.save()
    return True, ""
