from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class Action(TimeStampedModel):
    KIND_ACTION = "actie"
    KIND_ESCALATION = "escalatie"
    KIND_CHOICES = [(KIND_ACTION, "Actie"), (KIND_ESCALATION, "Escalatie")]
    STATUS_CHOICES = [
        ("open", "Open"),
        ("bezig", "In behandeling"),
        ("wacht", "Wacht op derden"),
        ("gereed", "Gereed"),
        ("vervallen", "Vervallen"),
    ]
    OPEN_STATUSES = ["open", "bezig", "wacht"]
    PRIORITY_CHOICES = [(1, "Laag"), (2, "Normaal"), (3, "Hoog"), (4, "Urgent")]
    LEVEL_CHOICES = [
        (1, "1 - Teamleider / supervisor"),
        (2, "2 - OPS management"),
        (3, "3 - Directie"),
        (4, "4 - Extern (klant / rederij / vervoerder)"),
    ]

    title = models.CharField("titel", max_length=250)
    description = models.TextField("omschrijving", blank=True)
    kind = models.CharField("soort", max_length=20, choices=KIND_CHOICES, default=KIND_ACTION)
    status = models.CharField("status", max_length=20, choices=STATUS_CHOICES, default="open")
    priority = models.PositiveSmallIntegerField("prioriteit", choices=PRIORITY_CHOICES, default=2)
    escalation_level = models.PositiveSmallIntegerField("escalatieniveau", choices=LEVEL_CHOICES, null=True, blank=True)
    escalated_to = models.CharField("geëscaleerd naar", max_length=150, blank=True)
    owner = models.ForeignKey(
        "planning.Employee", verbose_name="eigenaar", null=True, blank=True, on_delete=models.SET_NULL, related_name="actions"
    )
    due_date = models.DateField("deadline", null=True, blank=True)
    customer = models.ForeignKey(
        "core.Customer", verbose_name="klant", null=True, blank=True, on_delete=models.SET_NULL, related_name="actions"
    )
    sea_shipment = models.ForeignKey(
        "shipments.SeaShipment", verbose_name="zeevracht dossier", null=True, blank=True, on_delete=models.SET_NULL, related_name="actions"
    )
    road_transport = models.ForeignKey(
        "shipments.RoadTransport", verbose_name="wegtransport", null=True, blank=True, on_delete=models.SET_NULL, related_name="actions"
    )
    meeting_item = models.ForeignKey(
        "meetings.MeetingItem", verbose_name="uit overlegpunt", null=True, blank=True, on_delete=models.SET_NULL, related_name="actions"
    )
    resolution = models.TextField("oplossing / afhandeling", blank=True)
    completed_at = models.DateTimeField("afgerond op", null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-priority", "due_date", "-created_at"]
        verbose_name = "actie / escalatie"
        verbose_name_plural = "acties & escalaties"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.status in ("gereed", "vervallen") and not self.completed_at:
            self.completed_at = timezone.now()
        elif self.status in self.OPEN_STATUSES:
            self.completed_at = None
        if self.kind == self.KIND_ESCALATION and not self.escalation_level:
            self.escalation_level = 1
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def is_overdue(self):
        return self.is_open and self.due_date is not None and self.due_date < timezone.localdate()

    @property
    def total_costs(self):
        return sum((c.amount for c in self.costs.all()), Decimal("0"))


class ExtraCost(TimeStampedModel):
    RESP_CUSTOMER = "klant"
    RESP_CORY = "cory"
    RESP_CARRIER = "vervoerder"
    RESP_FORCE_MAJEURE = "overmacht"
    RESPONSIBILITY_CHOICES = [
        (RESP_CUSTOMER, "Klant"),
        (RESP_CORY, "Wij (Cory Brothers)"),
        (RESP_CARRIER, "Vervoerder / rederij"),
        (RESP_FORCE_MAJEURE, "Overmacht"),
    ]
    TYPE_CHOICES = [
        ("demurrage", "Demurrage"),
        ("detention", "Detention"),
        ("opslag", "Opslag / plugin"),
        ("keuring", "Keurkosten / extra inspectie"),
        ("wachttijd", "Wachttijd vervoerder"),
        ("transport", "Extra transport / herlevering"),
        ("douane", "Douane"),
        ("overig", "Overig"),
    ]
    STATUS_CHOICES = [
        ("open", "Nog beoordelen"),
        ("doorbelasten", "Door te belasten"),
        ("doorbelast", "Doorbelast / gefactureerd"),
        ("geclaimd", "Geclaimd bij vervoerder"),
        ("afgeboekt", "Afgeboekt (eigen kosten)"),
    ]

    action = models.ForeignKey(
        Action, verbose_name="actie / escalatie", null=True, blank=True, on_delete=models.CASCADE, related_name="costs"
    )
    customer = models.ForeignKey(
        "core.Customer", verbose_name="klant", null=True, blank=True, on_delete=models.SET_NULL, related_name="extra_costs"
    )
    sea_shipment = models.ForeignKey(
        "shipments.SeaShipment", verbose_name="zeevracht dossier", null=True, blank=True, on_delete=models.SET_NULL, related_name="extra_costs"
    )
    road_transport = models.ForeignKey(
        "shipments.RoadTransport", verbose_name="wegtransport", null=True, blank=True, on_delete=models.SET_NULL, related_name="extra_costs"
    )
    cost_type = models.CharField("soort kosten", max_length=20, choices=TYPE_CHOICES, default="overig")
    description = models.CharField("omschrijving", max_length=250)
    amount = models.DecimalField("bedrag", max_digits=12, decimal_places=2)
    currency = models.CharField("valuta", max_length=3, default="EUR")
    responsibility = models.CharField("verantwoordelijk", max_length=20, choices=RESPONSIBILITY_CHOICES)
    status = models.CharField("status", max_length=20, choices=STATUS_CHOICES, default="open")
    cost_date = models.DateField("datum", default=timezone.localdate)
    invoice_reference = models.CharField("factuur- / claimreferentie", max_length=100, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-cost_date", "-created_at"]
        verbose_name = "extra kosten"
        verbose_name_plural = "extra kosten"

    def __str__(self):
        return f"{self.description} ({self.currency} {self.amount})"

    def save(self, *args, **kwargs):
        # Neem klant/dossier over van de actie als die niet apart is ingevuld.
        if self.action_id:
            self.customer_id = self.customer_id or self.action.customer_id
            self.sea_shipment_id = self.sea_shipment_id or self.action.sea_shipment_id
            self.road_transport_id = self.road_transport_id or self.action.road_transport_id
        if not self.customer_id:
            source = self.sea_shipment or self.road_transport
            if source is not None:
                self.customer_id = source.customer_id
        super().save(*args, **kwargs)
