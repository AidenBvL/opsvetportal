from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel

from .validators import normalize_container_number, validate_container_number

INSPECTION_STATUS_CHOICES = [
    ("n.v.t.", "Niet keuringsplichtig"),
    ("aan_te_melden", "Nog aanmelden (CHED)"),
    ("aangemeld", "Aangemeld bij keurpunt"),
    ("documentair", "Documentcontrole"),
    ("gepland", "Fysieke keuring gepland"),
    ("in_keuring", "In keuring"),
    ("vrijgegeven", "Vrijgegeven"),
    ("afgekeurd", "Afgekeurd / geweigerd"),
]


class SeaShipment(TimeStampedModel):
    STATUS_CHOICES = [
        ("verwacht", "Verwacht / onderweg"),
        ("aangekomen", "Aangekomen (gelost)"),
        ("keuring", "In keuring / douane"),
        ("vrij", "Vrijgegeven"),
        ("uitgeleverd", "Uitgeleverd"),
        ("afgerond", "Afgerond"),
        ("geannuleerd", "Geannuleerd"),
    ]
    OPEN_STATUSES = ["verwacht", "aangekomen", "keuring", "vrij"]
    CONTAINER_TYPE_CHOICES = [
        ("20DV", "20' Dry"),
        ("40DV", "40' Dry"),
        ("40HC", "40' High Cube"),
        ("20RF", "20' Reefer"),
        ("40RH", "40' Reefer High Cube"),
        ("other", "Overig"),
    ]

    customer = models.ForeignKey("core.Customer", verbose_name="klant", on_delete=models.PROTECT, related_name="sea_shipments")
    customer_reference = models.CharField("klantreferentie", max_length=100, blank=True)
    cory_reference = models.CharField("Cory referentie", max_length=100, blank=True, db_index=True)
    container_number = models.CharField(
        "containernummer", max_length=11, validators=[validate_container_number], db_index=True
    )
    container_type = models.CharField("containertype", max_length=10, choices=CONTAINER_TYPE_CHOICES, default="40RH")
    seal_number = models.CharField("zegelnummer", max_length=50, blank=True)
    shipping_line = models.ForeignKey(
        "core.ShippingLine", verbose_name="rederij", null=True, blank=True, on_delete=models.PROTECT, related_name="shipments"
    )
    bl_number = models.CharField("B/L-nummer", max_length=60, blank=True, db_index=True)
    booking_number = models.CharField("boekingsnummer", max_length=60, blank=True)

    # Schip en reis (automatisch bijgewerkt door tracking)
    vessel_name = models.CharField("zeeschip (vessel)", max_length=150, blank=True)
    vessel_imo = models.CharField("IMO", max_length=10, blank=True)
    voyage = models.CharField("reisnummer", max_length=40, blank=True)
    original_vessel_name = models.CharField("oorspronkelijk zeeschip", max_length=150, blank=True)
    vessel_changed = models.BooleanField("van schip gewisseld", default=False)
    vessel_changed_at = models.DateTimeField("schipwissel gedetecteerd op", null=True, blank=True)
    port_of_loading = models.CharField(
        "laadhaven (POL)", max_length=100, blank=True, help_text="UN/LOCODE of havennaam; bekende havens worden omgezet naar de code."
    )
    port_of_discharge = models.CharField(
        "loshaven (POD)", max_length=100, default="NLRTM", help_text="UN/LOCODE of havennaam, bijv. NLRTM of Rotterdam."
    )
    terminal = models.CharField("terminal", max_length=100, blank=True)

    departed_at = models.DateTimeField("vertrokken uit laadhaven (ATD)", null=True, blank=True)
    eta = models.DateTimeField("ETA", null=True, blank=True)
    eta_original = models.DateTimeField("oorspronkelijke ETA", null=True, blank=True)
    ata = models.DateTimeField("ATA (werkelijke aankomst)", null=True, blank=True)
    discharged_at = models.DateTimeField("gelost op", null=True, blank=True)
    free_time_until = models.DateField("vrije dagen t/m (demurrage)", null=True, blank=True)

    # Keuring
    inspection_required = models.BooleanField("keuringsplichtig", default=True)
    inspection_point = models.ForeignKey(
        "core.InspectionPoint", verbose_name="keurpunt", null=True, blank=True, on_delete=models.PROTECT, related_name="sea_shipments"
    )
    ched_number = models.CharField("CHED-nummer (TRACES)", max_length=60, blank=True)
    inspection_status = models.CharField("keuringsstatus", max_length=20, choices=INSPECTION_STATUS_CHOICES, default="aan_te_melden")
    inspection_planned_at = models.DateTimeField("keuring gepland op", null=True, blank=True)
    customs_cleared = models.BooleanField("douane vrij", default=False)

    goods_description = models.CharField("goederenomschrijving", max_length=250, blank=True)
    temperature_setpoint = models.DecimalField("temperatuur setpoint (°C)", max_digits=5, decimal_places=1, null=True, blank=True)
    gross_weight_kg = models.DecimalField("brutogewicht (kg)", max_digits=12, decimal_places=3, null=True, blank=True)
    packages = models.PositiveIntegerField("colli", null=True, blank=True)
    package_type = models.CharField("verpakking", max_length=40, blank=True, help_text="Bijv. CARTONS, PALLETS.")

    status = models.CharField("status", max_length=20, choices=STATUS_CHOICES, default="verwacht")
    handler = models.ForeignKey(
        "planning.Employee", verbose_name="behandelaar", null=True, blank=True, on_delete=models.SET_NULL, related_name="sea_shipments"
    )
    notes = models.TextField("opmerkingen", blank=True)

    tracking_enabled = models.BooleanField("automatische tracking", default=True)
    tracking_last_checked = models.DateTimeField("laatst gecontroleerd", null=True, blank=True)
    tracking_last_error = models.CharField("laatste trackingfout", max_length=300, blank=True)
    external_tracking_id = models.CharField("extern tracking-ID", max_length=60, blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["eta", "container_number"]
        verbose_name = "zeevracht dossier"
        verbose_name_plural = "zeevracht dossiers"
        permissions = [("refresh_tracking", "Mag tracking handmatig verversen")]

    def __str__(self):
        ref = self.cory_reference or self.customer_reference
        return f"{self.container_number} ({ref})" if ref else self.container_number

    def save(self, *args, **kwargs):
        from core.ports import port_code, terminal_name

        self.container_number = normalize_container_number(self.container_number)
        self.port_of_loading = port_code(self.port_of_loading)
        self.port_of_discharge = port_code(self.port_of_discharge) or "NLRTM"
        self.terminal = terminal_name(self.terminal, self.port_of_discharge)
        if self.vessel_name and not self.original_vessel_name:
            self.original_vessel_name = self.vessel_name
        if self.eta and not self.eta_original:
            self.eta_original = self.eta
        if not self.inspection_required:
            self.inspection_status = "n.v.t."
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def eta_delay_hours(self):
        if self.eta and self.eta_original:
            return round((self.eta - self.eta_original).total_seconds() / 3600)
        return 0

    @property
    def voyage_progress(self):
        """Percentage van de zeereis (vertrek → ETA), of None als dat niet te bepalen is."""
        end = self.ata or self.eta
        if self.ata:
            return 100
        if not self.departed_at or not end or end <= self.departed_at:
            return None
        done = (timezone.now() - self.departed_at) / (end - self.departed_at)
        return max(0, min(99, round(done * 100)))

    @property
    def days_to_eta(self):
        if not self.eta or self.ata:
            return None
        return (timezone.localtime(self.eta).date() - timezone.localdate()).days

    @property
    def free_days_left(self):
        if not self.free_time_until:
            return None
        return (self.free_time_until - timezone.localdate()).days

    @property
    def carrier_tracking_url(self):
        line = self.shipping_line
        if not line or not line.tracking_url_template:
            return ""
        number = self.bl_number or self.booking_number or self.container_number
        return line.tracking_url_template.replace("{container}", self.container_number).replace("{number}", number)

    @property
    def active_road_transports(self):
        """Niet-geannuleerde wegtransporten, vroegste eerst (gebruikt de prefetch van de lijst)."""
        transports = [r for r in self.road_transports.all() if r.status != "geannuleerd"]
        return sorted(transports, key=lambda r: (r.loading_at is None, r.loading_at or r.created_at))

    @property
    def attention(self):
        """Wat aandacht vraagt, als (niveau, tekst): danger, warning of info."""
        if not self.is_open:
            return []
        flags = []
        days = self.days_to_eta
        soon = bool(self.ata) or (days is not None and days <= 3)
        if self.vessel_changed:
            flags.append(("danger", "Schipwissel"))
        if self.inspection_required and self.inspection_status == "aan_te_melden":
            flags.append(("danger" if soon else "warning", "CHED aanmelden"))
        left = self.free_days_left
        if left is not None:
            if left < 0:
                flags.append(("danger", f"Vrije dagen {-left} d verlopen"))
            elif left <= 2:
                flags.append(("danger" if left == 0 else "warning", "Laatste vrije dag" if left == 0 else f"Nog {left} vrije dag{'en' if left > 1 else ''}"))
        if not self.active_road_transports and (self.ata or (days is not None and days <= 5)):
            flags.append(("warning", "Transport plannen"))
        if self.eta_delay_hours >= 24:
            flags.append(("info", f"{self.eta_delay_hours} u vertraagd"))
        if self.tracking_last_error:
            flags.append(("info", "Trackingfout"))
        return flags

    @property
    def attention_score(self):
        weights = {"danger": 10, "warning": 3, "info": 1}
        return sum(weights[level] for level, _text in self.attention)

    @property
    def demurrage_risk(self):
        if not self.free_time_until or not self.is_open:
            return False
        return (self.free_time_until - timezone.localdate()).days <= 2


class TrackingUpdate(models.Model):
    shipment = models.ForeignKey(SeaShipment, on_delete=models.CASCADE, related_name="tracking_updates")
    checked_at = models.DateTimeField("gecontroleerd op", default=timezone.now)
    provider = models.CharField("bron", max_length=30)
    success = models.BooleanField(default=True)
    eta = models.DateTimeField("ETA", null=True, blank=True)
    ata = models.DateTimeField("ATA", null=True, blank=True)
    vessel_name = models.CharField("schip", max_length=150, blank=True)
    vessel_imo = models.CharField("IMO", max_length=10, blank=True)
    voyage = models.CharField("reis", max_length=40, blank=True)
    eta_changed = models.BooleanField("ETA gewijzigd", default=False)
    vessel_changed = models.BooleanField("schip gewisseld", default=False)
    message = models.CharField("melding", max_length=300, blank=True)
    raw = models.JSONField("ruwe respons", null=True, blank=True)

    class Meta:
        ordering = ["-checked_at"]
        verbose_name = "trackingupdate"
        verbose_name_plural = "trackingupdates"

    def __str__(self):
        return f"{self.shipment} @ {self.checked_at:%d-%m %H:%M}"


class RoadTransport(TimeStampedModel):
    DIRECTION_CHOICES = [
        ("import", "Import: haven/keurpunt → klant"),
        ("export", "Export: klant → haven"),
        ("nationaal", "Binnenland / overig"),
    ]
    TYPE_CHOICES = [
        ("container", "Containertransport (container op chassis)"),
        ("koeltrailer", "Koeltrailer / losse lading"),
        ("overig", "Overig"),
    ]
    STATUS_CHOICES = [
        ("gepland", "Gepland"),
        ("onderweg", "Onderweg"),
        ("keurpunt", "Bij keurpunt"),
        ("geleverd", "Geleverd"),
        ("afgerond", "Afgerond"),
        ("geannuleerd", "Geannuleerd"),
    ]
    OPEN_STATUSES = ["gepland", "onderweg", "keurpunt"]

    customer = models.ForeignKey("core.Customer", verbose_name="klant", on_delete=models.PROTECT, related_name="road_transports")
    customer_reference = models.CharField("klantreferentie", max_length=100, blank=True)
    cory_reference = models.CharField("Cory referentie", max_length=100, blank=True, db_index=True)
    direction = models.CharField(
        "richting", max_length=20, choices=DIRECTION_CHOICES, default="import",
        help_text="Import: de container wordt opgehaald bij de terminal (eventueel via het keurpunt) en bij de klant gelost.",
    )
    transport_type = models.CharField("soort transport", max_length=20, choices=TYPE_CHOICES, default="container")
    carrier = models.ForeignKey(
        "core.RoadCarrier", verbose_name="vervoerder", null=True, blank=True, on_delete=models.PROTECT, related_name="transports"
    )
    sea_shipment = models.ForeignKey(
        SeaShipment, verbose_name="gekoppelde zeecontainer", null=True, blank=True, on_delete=models.SET_NULL, related_name="road_transports"
    )
    truck_plate = models.CharField("kenteken trekker", max_length=20, blank=True)
    trailer_plate = models.CharField("kenteken trailer", max_length=20, blank=True)
    driver_name = models.CharField("chauffeur", max_length=100, blank=True)
    driver_phone = models.CharField("telefoon chauffeur", max_length=50, blank=True)
    cmr_number = models.CharField("CMR-nummer", max_length=60, blank=True)

    loading_address = models.ForeignKey(
        "core.Address", verbose_name="laadadres uit adresboek", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    loading_place = models.CharField("laadadres", max_length=250, blank=True, help_text="Bijv. de terminal waar de container staat.")
    loading_reference = models.CharField("referentie ophalen", max_length=100, blank=True, help_text="Pincode / release- of pick-upreferentie.")
    loading_at = models.DateTimeField("laden gepland", null=True, blank=True)
    unloading_address = models.ForeignKey(
        "core.Address", verbose_name="losadres uit adresboek", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    unloading_place = models.CharField("losadres", max_length=250, blank=True)
    unloading_reference = models.CharField("referentie lossen", max_length=100, blank=True, help_text="Ordernummer of tijdslot bij de ontvanger.")
    delivery_planned_at = models.DateTimeField("levering gepland", null=True, blank=True)
    delivery_window_until = models.DateTimeField("levering uiterlijk", null=True, blank=True, help_text="Einde van het tijdvenster.")
    delivered_at = models.DateTimeField("geleverd op", null=True, blank=True)
    driver_instructions = models.TextField("instructies voor de chauffeur", blank=True)
    empty_return_place = models.CharField("lege container retour naar", max_length=200, blank=True, help_text="Depot of terminal.")
    empty_return_by = models.DateField("lege retour uiterlijk", null=True, blank=True)

    inspection_required = models.BooleanField("keuringsplichtig", default=True)
    inspection_point = models.ForeignKey(
        "core.InspectionPoint", verbose_name="keurpunt", null=True, blank=True, on_delete=models.PROTECT, related_name="road_transports"
    )
    ched_number = models.CharField("CHED-nummer (TRACES)", max_length=60, blank=True)
    inspection_status = models.CharField("keuringsstatus", max_length=20, choices=INSPECTION_STATUS_CHOICES, default="aan_te_melden")
    inspection_planned_at = models.DateTimeField("keuring gepland op", null=True, blank=True)

    goods_description = models.CharField("goederenomschrijving", max_length=250, blank=True)
    temperature_setpoint = models.DecimalField("temperatuur (°C)", max_digits=5, decimal_places=1, null=True, blank=True)
    pallets = models.PositiveIntegerField("pallets", null=True, blank=True)
    gross_weight_kg = models.DecimalField("brutogewicht (kg)", max_digits=12, decimal_places=3, null=True, blank=True)

    status = models.CharField("status", max_length=20, choices=STATUS_CHOICES, default="gepland")
    handler = models.ForeignKey(
        "planning.Employee", verbose_name="behandelaar", null=True, blank=True, on_delete=models.SET_NULL, related_name="road_transports"
    )
    notes = models.TextField("opmerkingen", blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["loading_at", "-created_at"]
        verbose_name = "wegtransport"
        verbose_name_plural = "wegtransporten"

    def __str__(self):
        ref = self.cory_reference or self.customer_reference or f"#{self.pk}"
        return f"{ref} - {self.customer}"

    def save(self, *args, **kwargs):
        if not self.inspection_required:
            self.inspection_status = "n.v.t."
        # Een gekozen adres uit het adresboek vult het adresveld (als dat nog leeg is).
        if self.loading_address_id and not self.loading_place:
            self.loading_place = self.loading_address.one_line[:250]
        if self.unloading_address_id and not self.unloading_place:
            self.unloading_place = self.unloading_address.one_line[:250]
        if self.unloading_address_id and not self.driver_instructions and self.unloading_address.instructions:
            self.driver_instructions = self.unloading_address.instructions
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES
