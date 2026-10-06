from django import forms

from planning.models import Employee

from .models import Action, ExtraCost


class ActionForm(forms.ModelForm):
    class Meta:
        model = Action
        fields = ["title", "kind", "status", "priority", "escalation_level", "escalated_to", "owner", "due_date",
                  "customer", "sea_shipment", "road_transport", "description", "resolution"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "description": forms.Textarea(attrs={"rows": 3}),
            "resolution": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = Employee.objects.filter(active=True)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("kind") == Action.KIND_ESCALATION and not cleaned.get("escalation_level"):
            cleaned["escalation_level"] = 1
        return cleaned


class ExtraCostForm(forms.ModelForm):
    class Meta:
        model = ExtraCost
        fields = ["action", "customer", "sea_shipment", "road_transport", "cost_type", "description", "amount",
                  "currency", "responsibility", "status", "cost_date", "invoice_reference"]
        widgets = {
            "cost_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "responsibility": forms.RadioSelect,
        }


class InlineCostForm(forms.ModelForm):
    class Meta:
        model = ExtraCost
        fields = ["cost_type", "description", "amount", "currency", "responsibility", "status"]
        widgets = {"responsibility": forms.RadioSelect}
