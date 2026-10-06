import mimetypes
import os
import tempfile
from contextlib import contextmanager

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
    # Kopie van het bestand in de database: de schijf van de webserver (Render) is niet blijvend.
    content = models.BinaryField("inhoud", null=True, blank=True, editable=False)
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
        return os.path.splitext(self.original_name or self.file.name)[1].lower()

    @property
    def content_type(self):
        return mimetypes.guess_type(f"x{self.extension}")[0] or "application/octet-stream"

    @property
    def icon(self):
        if self.extension == ".pdf":
            return "bi-file-earmark-pdf"
        if self.extension in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
            return "bi-file-earmark-image"
        return "bi-file-earmark-text"

    def store_content(self):
        """Bewaar de bytes van het (net geüploade) bestand ook in de database."""
        if self.file._committed:
            with self.file.open("rb") as fh:
                self.content = fh.read()
            return
        upload = self.file.file
        upload.seek(0)
        self.content = upload.read()
        upload.seek(0)

    def read_bytes(self):
        if self.content:
            return bytes(self.content)
        with self.file.open("rb") as fh:
            return fh.read()

    @contextmanager
    def local_file(self):
        """Pad naar het bestand op schijf; staat het er niet meer, dan tijdelijk uit de database."""
        try:
            path = self.file.path if self.file else ""
        except (NotImplementedError, ValueError):
            path = ""
        if path and os.path.exists(path):
            yield path
            return
        if not self.content:
            raise FileNotFoundError("Het bestand is niet meer aanwezig. Upload het opnieuw.")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = os.path.join(tmp, f"document{self.extension}")
            with open(tmp_path, "wb") as fh:
                fh.write(bytes(self.content))
            yield tmp_path
