from django import forms

from planning.models import Employee

from .models import RoadTransport, SeaShipment, TransportStop

DT = {"type": "datetime-local"}
DT_FORMAT = "%Y-%m-%dT%H:%M"


class PortInput(forms.TextInput):
    """Tekstveld voor een haven: code of naam typen, met suggesties en de volledige naam eronder."""

    def render(self, name, value, attrs=None, renderer=None):
        from django.utils.html import format_html, format_html_join

        from core.ports import port_full_name, port_index

        list_id = f"ports-{name}"
        attrs = {**(attrs or {}), "list": list_id, "autocomplete": "off", "data-port-input": ""}
        index = port_index()
        # Alleen containerhavens als suggestie (alle 17.000+ zeehavens worden wel herkend bij het opslaan).
        codes = sorted((index["container"] & set(index["codes"])) | ({str(value).upper()} & set(index["codes"]) if value else set()))
        options = format_html_join("", '<option value="{}">{}</option>', ((code, port_full_name(code)) for code in codes))
        return super().render(name, value, attrs, renderer) + format_html(
            '<datalist id="{}">{}</datalist><div class="form-text port-name" data-port-name>{}</div>',
            list_id, options, port_full_name(value) if value else "",
        )


class TerminalInput(forms.TextInput):
    """Tekstveld met terminals als suggestie (die van de loshaven, als die bekend is) en de volledige gegevens eronder."""

    port = ""

    def render(self, name, value, attrs=None, renderer=None):
        from django.utils.html import format_html, format_html_join

        from core.ports import port_index, terminal_label

        list_id = f"terminals-{name}"
        terminals = port_index()["terminals"]
        if self.port:
            terminals = [t for t in terminals if t["locode"] == self.port] or terminals
        options = format_html_join("", '<option value="{}">{}</option>', ((t["label"], t["locode"]) for t in terminals))
        attrs = {**(attrs or {}), "list": list_id, "autocomplete": "off"}
        return super().render(name, value, attrs, renderer) + format_html(
            '<datalist id="{}">{}</datalist><div class="form-text">{}</div>', list_id, options,
            terminal_label(value, self.port) if value else "",
        )


def _dt(field_names):
    return {name: forms.DateTimeInput(attrs=DT, format=DT_FORMAT) for name in field_names}


class SeaShipmentForm(forms.ModelForm):
    class Meta:
        model = SeaShipment
        fields = [
            "customer", "customer_reference", "cory_reference", "container_number", "container_type", "seal_number",
            "shipping_line", "bl_number", "booking_number", "vessel_name", "voyage", "port_of_loading",
            "port_of_discharge", "terminal", "departed_at", "eta", "ata", "free_time_until", "inspection_required", "inspection_point",
            "ched_number", "inspection_status", "inspection_planned_at", "customs_cleared", "carrier_release", "carrier_released_at",
            "release_reference", "local_charges", "local_charges_amount", "local_charges_paid_at", "invoice_status",
            "invoice_requested_at", "invoice_received_at", "lab_status", "lab_sampled_at",
            "lab_expected_at", "lab_result_at", "lab_notes", "goods_description",
            "temperature_setpoint", "gross_weight_kg", "packages", "package_type", "status", "handler", "tracking_enabled", "notes",
        ]
        widgets = {
            **_dt(["departed_at", "eta", "ata", "inspection_planned_at", "lab_sampled_at", "lab_result_at", "carrier_released_at",
                   "local_charges_paid_at", "invoice_requested_at", "invoice_received_at"]),
            "lab_expected_at": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "free_time_until": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "port_of_loading": PortInput(),
            "port_of_discharge": PortInput(),
            "terminal": TerminalInput(),
        }
        help_texts = {"vessel_name": "Wordt automatisch bijgewerkt via tracking.", "eta": "Wordt automatisch bijgewerkt via tracking."}

    sections = [
        ("Klant & referenties", "building", ["customer", "customer_reference", "cory_reference", "handler", "status"]),
        ("Container", "box", ["container_number", "container_type", "seal_number", "bl_number", "booking_number"]),
        ("Reis", "water", ["shipping_line", "vessel_name", "voyage", "port_of_loading", "port_of_discharge", "terminal",
                           "departed_at", "eta", "ata", "free_time_until", "tracking_enabled"]),
        ("Keuring & douane", "clipboard2-check", ["inspection_required", "inspection_point", "ched_number", "inspection_status",
                                                 "inspection_planned_at", "customs_cleared"]),
        ("Vrijgave & kosten", "unlock", ["carrier_release", "carrier_released_at", "release_reference", "local_charges",
                                         "local_charges_amount", "local_charges_paid_at", "invoice_status", "invoice_requested_at",
                                         "invoice_received_at"]),
        ("Labonderzoek", "eyedropper", ["lab_status", "lab_sampled_at", "lab_expected_at", "lab_result_at", "lab_notes"]),
        ("Lading", "thermometer-snow", ["goods_description", "temperature_setpoint", "gross_weight_kg", "packages", "package_type"]),
        ("Opmerkingen", "chat-left-text", ["notes"]),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["terminal"].widget.port = self.instance.port_of_discharge or self.initial.get("port_of_discharge", "")
        self.fields["handler"].queryset = Employee.objects.filter(active=True)
        for name in ("customer", "shipping_line", "inspection_point"):
            qs = self.fields[name].queryset
            self.fields[name].queryset = qs.filter(active=True) if not self.instance.pk else qs

    def clean_container_number(self):
        from .validators import normalize_container_number

        return normalize_container_number(self.cleaned_data["container_number"])


class AddressSelect(forms.Select):
    """Keuzelijst uit het adresboek; elke optie draagt het adres en de instructies mee zodat het formulier ze kan invullen."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        address = getattr(value, "instance", None)
        if address is not None:
            hours = f"Ontvangst: {address.opening_hours}" if address.opening_hours else ""
            slot = "Tijdslot/vooraanmelding verplicht" if address.booking_required else ""
            option["attrs"].update({
                "data-place": address.one_line,
                "data-instructions": "\n".join(p for p in [slot, hours, address.instructions] if p),
            })
        return option


class RoadTransportForm(forms.ModelForm):
    save_unloading_address = forms.BooleanField(
        label="Losadres bewaren in het adresboek", required=False,
        help_text="Voor een nieuw adres dat je hierboven hebt getypt; daarna kies je het de volgende keer gewoon uit de lijst.",
    )

    class Meta:
        model = RoadTransport
        fields = [
            "customer", "customer_reference", "cory_reference", "direction", "transport_type", "carrier", "sea_shipment",
            "truck_plate", "trailer_plate", "driver_name", "driver_phone", "cmr_number",
            "loading_address", "loading_place", "loading_reference", "loading_at",
            "unloading_address", "unloading_place", "unloading_reference", "delivery_planned_at", "delivery_window_until",
            "delivered_at", "driver_instructions", "empty_return_place", "empty_return_by",
            "inspection_required", "inspection_point", "ched_number", "inspection_status", "inspection_planned_at",
            "goods_description", "temperature_setpoint", "pallets", "gross_weight_kg", "status", "handler", "notes",
        ]
        widgets = {
            **_dt(["loading_at", "delivery_planned_at", "delivery_window_until", "delivered_at", "inspection_planned_at"]),
            "empty_return_by": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "loading_address": AddressSelect(attrs={"data-fill-place": "id_loading_place"}),
            "unloading_address": AddressSelect(attrs={"data-fill-place": "id_unloading_place", "data-fill-instructions": "id_driver_instructions"}),
            "driver_instructions": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    sections = [
        ("Klant & referenties", "building", ["customer", "customer_reference", "cory_reference", "direction", "transport_type",
                                            "sea_shipment", "handler", "status"]),
        ("Laden", "box-arrow-up", ["loading_address", "loading_place", "loading_reference", "loading_at"]),
        ("Lossen", "box-arrow-in-down", ["unloading_address", "unloading_place", "unloading_reference", "delivery_planned_at",
                                         "delivery_window_until", "delivered_at", "save_unloading_address"]),
        ("Chauffeur & vervoerder", "truck", ["carrier", "truck_plate", "trailer_plate", "driver_name", "driver_phone", "cmr_number",
                                             "driver_instructions"]),
        ("Lege container retour", "arrow-return-left", ["empty_return_place", "empty_return_by"]),
        ("Keuring", "clipboard2-check", ["inspection_required", "inspection_point", "ched_number", "inspection_status", "inspection_planned_at"]),
        ("Lading", "thermometer-snow", ["goods_description", "temperature_setpoint", "pallets", "gross_weight_kg"]),
        ("Opmerkingen", "chat-left-text", ["notes"]),
    ]

    def __init__(self, *args, **kwargs):
        from core.models import Address

        super().__init__(*args, **kwargs)
        self.fields["handler"].queryset = Employee.objects.filter(active=True)
        self.fields["sea_shipment"].queryset = SeaShipment.objects.select_related("customer").order_by("-created_at")
        addresses = Address.objects.filter(active=True).select_related("customer").order_by("customer__name", "name")
        self.fields["loading_address"].queryset = addresses.exclude(kind="los")
        self.fields["unloading_address"].queryset = addresses.exclude(kind="laad")
        for name in ("loading_address", "unloading_address"):
            self.fields[name].label_from_instance = (
                lambda a: f"{a} · {a.customer}" if a.customer_id else f"{a} · algemeen"
            )
            self.fields[name].help_text = "Kies een vast adres; adres en instructies worden dan ingevuld. Nieuw adres? Typ het hieronder."

    def save(self, commit=True):
        transport = super().save(commit=commit)
        data = self.cleaned_data
        if commit and data.get("save_unloading_address") and not transport.unloading_address_id and transport.unloading_place:
            transport.unloading_address = address_from_text(transport.unloading_place, transport.customer)
            transport.save(update_fields=["unloading_address", "updated_at"])
        return transport


class TransportStopForm(forms.ModelForm):
    class Meta:
        model = TransportStop
        fields = ["position", "kind", "inspection_point", "address", "place", "planned_arrival", "planned_departure",
                  "arrived_at", "departed_at", "reference", "notes"]
        widgets = {
            **_dt(["planned_arrival", "planned_departure", "arrived_at", "departed_at"]),
            "position": forms.HiddenInput(attrs={"data-stop-position": ""}),
            "kind": forms.Select(attrs={"data-stop-kind": ""}),
            # Suggesties uit één gedeelde lijst (zie _stops_formset.html) i.p.v. een lijst per stop.
            "place": forms.TextInput(attrs={"list": "stop-places", "autocomplete": "off"}),
        }

    def __init__(self, *args, **kwargs):
        from core.models import Address, InspectionPoint

        super().__init__(*args, **kwargs)
        self.fields["position"].required = False
        self.fields["inspection_point"].queryset = InspectionPoint.objects.filter(active=True)
        self.fields["address"].queryset = Address.objects.filter(active=True).select_related("customer").order_by("-kind", "name")
        self.fields["address"].label_from_instance = lambda a: f"{a} · {a.get_kind_display().split(' (')[0].lower()}"
        self.fields["place"].help_text = "Of typ een terminal / plaats."

    def clean(self):
        data = super().clean()
        if not self.cleaned_data.get("DELETE") and not (data.get("inspection_point") or data.get("address") or data.get("place")):
            raise forms.ValidationError("Kies een keurpunt of adres, of typ een plaats.")
        return data


def stops_formset(extra=0):
    return forms.inlineformset_factory(RoadTransport, TransportStop, form=TransportStopForm, extra=extra, can_delete=True)


def address_from_text(text, customer):
    """"Ter Maten, De Kooihoek 7, 3751 LZ Bunschoten" -> nieuw adres in het adresboek."""
    import re

    from core.models import Address

    parts = [p.strip() for p in re.split(r"[,\n]+", text) if p.strip()]
    country = "Nederland"
    if len(parts) > 1 and not re.search(r"\d", parts[-1]) and len(parts[-1].split()) <= 3 and len(parts) > 2:
        country = parts.pop()
    postal, city = "", parts[-1] if parts else text
    match = re.match(r"^(\d{4}\s?[A-Z]{2}|\d{4,5}|[A-Z]{1,2}-?\d{4,5})\s+(.+)$", city, re.I)
    if match:
        postal, city = match.group(1), match.group(2)
    company = parts[0] if len(parts) > 1 else ""
    street = parts[1] if len(parts) > 2 else ""
    return Address.objects.create(
        name=(company or city)[:100], customer=customer, company=company[:150], street=street[:150],
        postal_code=postal[:20], city=city[:100], country=country[:100],
    )


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
