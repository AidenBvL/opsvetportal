import os

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel



class Document(TimeStampedModel):
    TYPE_CHOICES = [
        ("bl", "Bill of Lading"),
        ("arrival_notice", "Arrival notice"),
        ("invoice", "Handelsfactuur"),
        ("packing_list", "Paklijst"),
        ("health_cert", "Gezondheidscertificaat"),
        ("ched", "CHED"),
        ("cmr", "CMR"),
        ("other", "Overig"),
    ]
    STATUS_CHOICES = [
        ("nieuw", "Nieuw"),
        ("verwerkt", "Tekst herkend"),
        ("gekoppeld", "Gekoppeld / dossiers aangemaakt"),
        ("fout", "Herkenning mislukt"),
    ]

    file = models.FileField("bestand", upload_to="documenten/%Y/%m/")
    original_name = models.CharField("bestandsnaam", max_length=255, blank=True)
    doc_type = models.CharField("soort document", max_length=30, choices=TYPE_CHOICES, default="bl")
    customer = models.ForeignKey(
        "core.Customer", verbose_name="klant", null=True, blank=True, on_delete=models.SET_NULL, related_name="documents"
    )
    sea_shipments = models.ManyToManyField(
        "shipments.SeaShipment", verbose_name="zeevracht dossiers", blank=True, related_name="documents"
    )
    road_transports = models.ManyToManyField(
        "shipments.RoadTransport", verbose_name="wegtransporten", blank=True, related_name="documents"
    )
    status = models.CharField("status", max_length=20, choices=STATUS_CHOICES, default="nieuw")
    extraction_method = models.CharField("herkenningsmethode", max_length=30, blank=True)
    extracted_text = models.TextField("herkende tekst", blank=True)
    extracted_data = models.JSONField("herkende gegevens", default=dict, blank=True)
    error = models.CharField("foutmelding", max_length=300, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "document"
        verbose_name_plural = "documenten"

    def __str__(self):
        return self.original_name or os.path.basename(self.file.name)

    @property
    def extension(self):
        return os.path.splitext(self.file.name)[1].lower()
