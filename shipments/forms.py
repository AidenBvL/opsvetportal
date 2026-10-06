from django import forms

from planning.models import Employee

from .models import RoadTransport, SeaShipment

DT = {"type": "datetime-local"}
DT_FORMAT = "%Y-%m-%dT%H:%M"


def _dt(field_names):
    return {name: forms.DateTimeInput(attrs=DT, format=DT_FORMAT) for name in field_names}


class SeaShipmentForm(forms.ModelForm):
    class Meta:
        model = SeaShipment
        fields = [
            "customer", "customer_reference", "cory_reference", "container_number", "container_type", "seal_number",
            "shipping_line", "bl_number", "booking_number", "vessel_name", "voyage", "port_of_loading",
            "port_of_discharge", "terminal", "eta", "ata", "free_time_until", "inspection_required", "inspection_point",
            "ched_number", "inspection_status", "inspection_planned_at", "customs_cleared", "goods_description",
            "temperature_setpoint", "gross_weight_kg", "packages", "status", "handler", "tracking_enabled", "notes",
        ]
        widgets = {
            **_dt(["eta", "ata", "inspection_planned_at"]),
            "free_time_until": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {"vessel_name": "Wordt automatisch bijgewerkt via tracking.", "eta": "Wordt automatisch bijgewerkt via tracking."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["handler"].queryset = Employee.objects.filter(active=True)
        for name in ("customer", "shipping_line", "inspection_point"):
            qs = self.fields[name].queryset
            self.fields[name].queryset = qs.filter(active=True) if not self.instance.pk else qs

    def clean_container_number(self):
        from .validators import normalize_container_number

        return normalize_container_number(self.cleaned_data["container_number"])


class RoadTransportForm(forms.ModelForm):
    class Meta:
        model = RoadTransport
        fields = [
            "customer", "customer_reference", "cory_reference", "direction", "carrier", "sea_shipment", "truck_plate",
            "trailer_plate", "driver_name", "driver_phone", "cmr_number", "loading_place", "loading_at",
            "unloading_place", "delivery_planned_at", "delivered_at", "inspection_required", "inspection_point",
            "ched_number", "inspection_status", "inspection_planned_at", "goods_description", "temperature_setpoint",
            "pallets", "gross_weight_kg", "status", "handler", "notes",
        ]
        widgets = {
            **_dt(["loading_at", "delivery_planned_at", "delivered_at", "inspection_planned_at"]),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["handler"].queryset = Employee.objects.filter(active=True)
        self.fields["sea_shipment"].queryset = SeaShipment.objects.select_related("customer").order_by("-created_at")


class BulkContainerForm(forms.Form):
    """Meerdere containers tegelijk aanmaken (bijv. alle containers van één B/L)."""

    customer = forms.ModelChoiceField(label="Klant", queryset=None)
    shipping_line = forms.ModelChoiceField(label="Rederij", queryset=None, required=False)
    inspection_point = forms.ModelChoiceField(label="Keurpunt", queryset=None, required=False)
    customer_reference = forms.CharField(label="Klantreferentie", required=False)
    cory_reference = forms.CharField(label="Cory referentie", required=False)
    bl_number = forms.CharField(label="B/L-nummer", required=False)
    vessel_name = forms.CharField(label="Zeeschip", required=False)
    voyage = forms.CharField(label="Reisnummer", required=False)
    eta = forms.DateTimeField(label="ETA", required=False, widget=forms.DateTimeInput(attrs=DT, format=DT_FORMAT))
    inspection_required = forms.BooleanField(label="Keuringsplichtig", required=False, initial=True)
    container_numbers = forms.CharField(
        label="Containernummers", widget=forms.Textarea(attrs={"rows": 5}),
        help_text="Eén per regel of gescheiden door komma's/spaties.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import Customer, InspectionPoint, ShippingLine

        self.fields["customer"].queryset = Customer.objects.filter(active=True)
        self.fields["shipping_line"].queryset = ShippingLine.objects.filter(active=True)
        self.fields["inspection_point"].queryset = InspectionPoint.objects.filter(active=True)

    def clean_container_numbers(self):
        import re

        from .validators import is_valid_container_number, normalize_container_number

        raw = re.split(r"[\s,;]+", self.cleaned_data["container_numbers"])
        numbers, invalid = [], []
        for value in raw:
            value = normalize_container_number(value)
            if not value:
                continue
            (numbers if is_valid_container_number(value) else invalid).append(value)
        if invalid:
            raise forms.ValidationError(f"Ongeldige containernummers: {', '.join(invalid)}")
        if not numbers:
            raise forms.ValidationError("Geen containernummers gevonden.")
        return list(dict.fromkeys(numbers))
