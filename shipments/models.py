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
    port_of_loading = models.CharField("laadhaven (POL)", max_length=100, blank=True)
    port_of_discharge = models.CharField("loshaven (POD)", max_length=100, default="NLRTM", help_text="UN/LOCODE, bijv. NLRTM.")
    terminal = models.CharField("terminal", max_length=100, blank=True)

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
    gross_weight_kg = models.DecimalField("brutogewicht (kg)", max_digits=10, decimal_places=1, null=True, blank=True)
    packages = models.PositiveIntegerField("colli", null=True, blank=True)

    status = models.CharField("status", max_length=20, choices=STATUS_CHOICES, default="verwacht")
    handler = models.ForeignKey(
        "planning.Employee", verbose_name="behandelaar", null=True, blank=True, on_delete=models.SET_NULL, related_name="sea_shipments"
    )
    notes = models.TextField("opmerkingen", blank=True)

    tracking_enabled = models.BooleanField("automatische tracking", default=True)
    tracking_last_checked = models.DateTimeField("laatst gecontroleerd", null=True, blank=True)
    tracking_last_error = models.CharField("laatste trackingfout", max_length=300, blank=True)
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
        self.container_number = normalize_container_number(self.container_number)
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
    DIRECTION_CHOICES = [("import", "Import (vanaf haven/keurpunt)"), ("export", "Export"), ("nationaal", "Nationaal / overig")]
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
    direction = models.CharField("richting", max_length=20, choices=DIRECTION_CHOICES, default="import")
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

    loading_place = models.CharField("laadadres", max_length=250, blank=True)
    loading_at = models.DateTimeField("laden gepland", null=True, blank=True)
    unloading_place = models.CharField("losadres", max_length=250, blank=True)
    delivery_planned_at = models.DateTimeField("levering gepland", null=True, blank=True)
    delivered_at = models.DateTimeField("geleverd op", null=True, blank=True)

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
    gross_weight_kg = models.DecimalField("brutogewicht (kg)", max_digits=10, decimal_places=1, null=True, blank=True)

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
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES
