from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class MeetingBlock(TimeStampedModel):
    """Eén overlegmoment op een dag: ochtend, middag of einde dag."""

    MORNING = "ochtend"
    AFTERNOON = "middag"
    END_OF_DAY = "einde_dag"
    BLOCK_CHOICES = [(MORNING, "Ochtendoverleg"), (AFTERNOON, "Middagoverleg"), (END_OF_DAY, "Einde-dag overleg")]
    BLOCK_ORDER = [MORNING, AFTERNOON, END_OF_DAY]

    date = models.DateField("datum")
    block = models.CharField("overleg", max_length=20, choices=BLOCK_CHOICES)
    attendees = models.ManyToManyField(
        "planning.Employee", verbose_name="aanwezig", blank=True, related_name="meeting_blocks"
    )
    notes = models.TextField("algemene notities", blank=True)

    class Meta:
        ordering = ["-date", "block"]
        unique_together = [("date", "block")]
        verbose_name = "overlegmoment"
        verbose_name_plural = "overlegmomenten"

    def __str__(self):
        return f"{self.get_block_display()} {self.date:%d-%m-%Y}"


class MeetingItem(TimeStampedModel):
    STATUS_CHOICES = [
        ("open", "Open"),
        ("beantwoord", "Beantwoord / afgehandeld"),
        ("doorgeschoven", "Doorgeschoven"),
    ]

    meeting = models.ForeignKey(MeetingBlock, on_delete=models.CASCADE, related_name="items", verbose_name="overleg")
    title = models.CharField("vraag / onderwerp", max_length=250)
    details = models.TextField("toelichting", blank=True)
    raised_by = models.ForeignKey(
        "planning.Employee",
        verbose_name="ingebracht door",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="raised_meeting_items",
    )
    colleagues = models.ManyToManyField(
        "planning.Employee", verbose_name="gekoppelde collega's", blank=True, related_name="meeting_items"
    )
    customer = models.ForeignKey(
        "core.Customer", verbose_name="klant", null=True, blank=True, on_delete=models.SET_NULL, related_name="meeting_items"
    )
    sea_shipment = models.ForeignKey(
        "shipments.SeaShipment",
        verbose_name="zeevracht dossier",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="meeting_items",
    )
    road_transport = models.ForeignKey(
        "shipments.RoadTransport",
        verbose_name="wegtransport",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="meeting_items",
    )
    status = models.CharField("status", max_length=20, choices=STATUS_CHOICES, default="open")
    answer = models.TextField("antwoord / besluit", blank=True)
    carried_from = models.ForeignKey(
        "self", verbose_name="doorgeschoven vanuit", null=True, blank=True, on_delete=models.SET_NULL, related_name="carried_to"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["meeting__date", "created_at"]
        verbose_name = "overlegpunt"
        verbose_name_plural = "overlegpunten"

    def __str__(self):
        return self.title
