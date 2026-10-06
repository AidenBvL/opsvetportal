from django import forms

from shipments.forms import BulkContainerForm

from .models import Document

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".txt"}


class UploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["file", "doc_type", "customer"]

    def clean_file(self):
        import os

        f = self.cleaned_data["file"]
        if os.path.splitext(f.name)[1].lower() not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError("Alleen PDF, afbeeldingen (PNG/JPG/TIFF) en tekstbestanden worden ondersteund.")
        if f.size > 25 * 1024 * 1024:
            raise forms.ValidationError("Bestand is groter dan 25 MB.")
        return f


class DocumentReviewForm(BulkContainerForm):
    booking_number = forms.CharField(label="Boekingsnummer", required=False)
    port_of_loading = forms.CharField(label="Laadhaven (POL)", required=False)
    port_of_discharge = forms.CharField(label="Loshaven (POD)", required=False, initial="NLRTM")
    ched_number = forms.CharField(label="CHED-nummer", required=False)
    goods_description = forms.CharField(label="Goederenomschrijving", required=False)
    temperature_setpoint = forms.DecimalField(label="Temperatuur (°C)", required=False, max_digits=5, decimal_places=1)

    field_order = ["customer", "customer_reference", "cory_reference", "shipping_line", "bl_number", "booking_number",
                   "vessel_name", "voyage", "eta", "port_of_loading", "port_of_discharge", "inspection_required",
                   "inspection_point", "ched_number", "goods_description", "temperature_setpoint", "container_numbers"]
