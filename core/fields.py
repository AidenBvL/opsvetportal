from django import forms
from django.db import models
from django.utils.text import capfirst

WEEKDAY_CHOICES = [
    (0, "maandag"),
    (1, "dinsdag"),
    (2, "woensdag"),
    (3, "donderdag"),
    (4, "vrijdag"),
    (5, "zaterdag"),
    (6, "zondag"),
]
WEEKDAY_SHORT = ["ma", "di", "wo", "do", "vr", "za", "zo"]


class WeekdaysField(models.CharField):
    """Slaat een set weekdagen (0 = maandag) op als "0,4"; levert een set[int] op."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 20)
        kwargs.setdefault("blank", True)
        kwargs.setdefault("default", set)
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def to_python(self, value):
        if isinstance(value, (set, frozenset, list, tuple)):
            return {int(v) for v in value}
        if not value:
            return set()
        return {int(v) for v in str(value).split(",") if v.strip() != ""}

    def get_prep_value(self, value):
        return ",".join(str(v) for v in sorted(self.to_python(value)))

    def value_to_string(self, obj):
        return self.get_prep_value(self.value_from_object(obj))

    def formfield(self, **kwargs):
        return forms.TypedMultipleChoiceField(
            choices=WEEKDAY_CHOICES,
            coerce=int,
            widget=forms.CheckboxSelectMultiple,
            required=not self.blank,
            label=capfirst(self.verbose_name),
            help_text=self.help_text,
        )


def weekdays_label(days):
    return ", ".join(WEEKDAY_SHORT[d] for d in sorted(days)) or "-"
