import datetime
from decimal import Decimal

from django import template
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def cell(obj, name):
    """Toon een veld netjes in een tabel (choices, booleans, datums, FK's)."""
    display = getattr(obj, f"get_{name}_display", None)
    if callable(display):
        return display()
    value = getattr(obj, name, "")
    if callable(value) and not isinstance(value, models.Manager):
        value = value()
    if isinstance(value, models.Manager):
        return ", ".join(str(v) for v in value.all()) or "-"
    if isinstance(value, bool):
        return mark_safe('<i class="bi bi-check-circle-fill text-success"></i>' if value else '<i class="bi bi-dash text-muted"></i>')
    if isinstance(value, datetime.datetime):
        return timezone.localtime(value).strftime("%d-%m-%Y %H:%M")
    if isinstance(value, datetime.date):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, (set, frozenset)):
        from core.fields import weekdays_label

        return weekdays_label(value)
    if value in (None, ""):
        return "-"
    return value


@register.filter
def euro(value):
    if value in (None, ""):
        return "-"
    value = Decimal(value).quantize(Decimal("0.01"))
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"€ {formatted}"


@register.simple_tag
def obj_url(url_name, obj):
    return reverse(url_name, args=[obj.pk])


@register.simple_tag(takes_context=True)
def querystring_with(context, **kwargs):
    params = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    return "?" + params.urlencode()


STATUS_COLORS = {
    "open": "secondary", "bezig": "primary", "wacht": "warning", "gereed": "success", "vervallen": "light",
    "verwacht": "info", "aangekomen": "primary", "keuring": "warning", "vrij": "success", "uitgeleverd": "success",
    "afgerond": "light", "geannuleerd": "light", "gepland": "info", "onderweg": "primary", "keurpunt": "warning",
    "geleverd": "success", "beantwoord": "success", "doorgeschoven": "warning",
    "aan_te_melden": "danger", "aangemeld": "info", "documentair": "info", "in_keuring": "warning",
    "vrijgegeven": "success", "afgekeurd": "danger", "n.v.t.": "light",
    "klant": "info", "cory": "danger", "vervoerder": "warning", "overmacht": "secondary",
    "wacht_collega": "warning", "wacht_planner": "info", "goedgekeurd": "success", "geweigerd": "secondary",
    "afgewezen": "danger", "ingetrokken": "light",
}  # fmt: skip


@register.simple_tag
def badge(value, label=None):
    color = STATUS_COLORS.get(str(value), "secondary")
    return format_html('<span class="chip chip-{}">{}</span>', "secondary" if color == "light" else color, label or value)


@register.filter
def priority_badge(action):
    colors = {1: "secondary", 2: "primary", 3: "warning", 4: "danger"}
    return format_html('<span class="chip chip-{}">{}</span>', colors.get(action.priority, "secondary"), action.get_priority_display())


@register.filter
def cnr(number):
    """Containernummer als 'MSKU 123450 [2]' (eigenaar, serienummer, controlecijfer)."""
    number = (number or "").strip()
    if len(number) != 11:
        return number
    return format_html('<span class="cnr">{} {}<i>{}</i></span>', number[:4], number[4:10], number[10])


@register.filter
def days_label(days):
    if days is None:
        return ""
    if days == 0:
        return "vandaag"
    if days == 1:
        return "morgen"
    if days == -1:
        return "gisteren"
    return f"over {days} dagen" if days > 0 else f"{-days} dagen geleden"


@register.filter
def isoformat(value):
    return value.isoformat() if value else ""


@register.filter
def get_item(mapping, key):
    if mapping is None:
        return None
    return mapping.get(key)


@register.filter
def bs(bound_field):
    """Render een formulierveld met de juiste Bootstrap-klasse."""
    from django import forms

    widget = bound_field.field.widget
    if isinstance(widget, (forms.CheckboxSelectMultiple, forms.RadioSelect)):  # noqa: SIM114
        css = "form-check-input"
    elif isinstance(widget, forms.CheckboxInput):
        css = "form-check-input"
    elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
        css = "form-select"
    else:
        css = "form-control"
    if bound_field.errors:
        css += " is-invalid"
    existing = widget.attrs.get("class", "")
    return bound_field.as_widget(attrs={"class": f"{existing} {css}".strip()})


@register.filter
def is_checkbox(bound_field):
    from django import forms

    return isinstance(bound_field.field.widget, forms.CheckboxInput)


@register.filter
def is_multi_checkbox(bound_field):
    from django import forms

    return isinstance(bound_field.field.widget, (forms.CheckboxSelectMultiple, forms.RadioSelect))


@register.filter
def get_item_index(sequence, index):
    try:
        return sequence[int(index)]
    except (IndexError, TypeError, ValueError):
        return ""


@register.filter
def split_pairs(value):
    """"a:A,b:B" -> [("a", "A"), ("b", "B")] voor kleine vaste lijstjes in templates."""
    return [tuple(part.split(":", 1)) for part in value.split(",")]


@register.simple_tag
def form_sections(form):
    """Groepeer velden volgens form.sections = [(titel, icoon, [velden]), ...]; de rest komt in 'Overig'."""
    sections = getattr(form, "sections", None)
    if not sections:
        return [{"title": "", "icon": "", "fields": list(form.visible_fields())}]
    used, result = set(), []
    for title, icon, names in sections:
        fields = [form[name] for name in names if name in form.fields]
        used.update(names)
        if fields:
            result.append({"title": title, "icon": icon, "fields": fields})
    rest = [f for f in form.visible_fields() if f.name not in used]
    if rest:
        result.append({"title": "Overig", "icon": "three-dots", "fields": rest})
    return result
