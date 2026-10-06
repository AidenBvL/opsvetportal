import os

from django import forms

from shipments.forms import BulkContainerForm

from .models import Document

# Bestanden waar tekst uit gelezen wordt.
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".txt"}
# Bij een zending mag ook ander papierwerk worden bewaard (Office, e-mails).
ATTACHMENT_EXTENSIONS = ALLOWED_EXTENSIONS | {".csv", ".doc", ".docx", ".xls", ".xlsx", ".msg", ".eml"}
MAX_SIZE = 25 * 1024 * 1024


def validate_upload(f, allowed=ALLOWED_EXTENSIONS):
    if os.path.splitext(f.name)[1].lower() not in allowed:
        if allowed is ALLOWED_EXTENSIONS:
            raise forms.ValidationError("Alleen PDF, afbeeldingen (PNG/JPG/TIFF) en tekstbestanden worden ondersteund.")
        raise forms.ValidationError(f"{f.name}: dit bestandstype wordt niet ondersteund.")
    if f.size > MAX_SIZE:
        raise forms.ValidationError(f"{f.name} is groter dan 25 MB.")
    return f


class UploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["file", "doc_type", "customer"]

    def clean_file(self):
        return validate_upload(self.cleaned_data["file"])


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(item, initial) for item in data]
        return [single(data, initial)]


class ShipmentUploadForm(forms.Form):
    """Eén of meer documenten direct bij een zending uploaden."""

    files = MultipleFileField(label="Bestanden")
    doc_type = forms.ChoiceField(label="Soort document", choices=Document.TYPE_CHOICES, initial="other")

    def clean_files(self):
        return [validate_upload(f, ATTACHMENT_EXTENSIONS) for f in self.cleaned_data["files"]]


class DocumentReviewForm(BulkContainerForm):
    booking_number = forms.CharField(label="Boekingsnummer", required=False)
    port_of_loading = forms.CharField(label="Laadhaven (POL)", required=False)
    port_of_discharge = forms.CharField(label="Loshaven (POD)", required=False, initial="NLRTM")
    departed_at = forms.DateField(
        label="Vertrokken (shipped on board)", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    ched_number = forms.CharField(label="CHED-nummer", required=False)
    goods_description = forms.CharField(label="Goederenomschrijving", required=False)
    temperature_setpoint = forms.DecimalField(label="Temperatuur (°C)", required=False, max_digits=5, decimal_places=1)

    field_order = ["customer", "customer_reference", "cory_reference", "shipping_line", "bl_number", "booking_number",
                   "vessel_name", "voyage", "departed_at", "eta", "port_of_loading", "port_of_discharge", "inspection_required",
                   "inspection_point", "ched_number", "goods_description", "temperature_setpoint", "container_numbers"]
