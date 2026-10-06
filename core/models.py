from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("aangemaakt op", auto_now_add=True)
    updated_at = models.DateTimeField("gewijzigd op", auto_now=True)

    class Meta:
        abstract = True


class Customer(TimeStampedModel):
    name = models.CharField("klantnaam", max_length=200, unique=True)
    code = models.CharField("klantcode", max_length=30, blank=True, help_text="Interne debiteur- of klantcode.")
    nationality = models.CharField("nationaliteit / land", max_length=100, blank=True)
    vat_number = models.CharField("btw-nummer", max_length=40, blank=True)
    eori_number = models.CharField("EORI-nummer", max_length=40, blank=True)
    street = models.CharField("straat + huisnummer", max_length=200, blank=True)
    postal_code = models.CharField("postcode", max_length=20, blank=True)
    city = models.CharField("plaats", max_length=100, blank=True)
    country = models.CharField("land", max_length=100, blank=True)
    contact_name = models.CharField("contactpersoon", max_length=150, blank=True)
    email = models.EmailField("e-mail", blank=True)
    phone = models.CharField("telefoon", max_length=50, blank=True)
    account_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="accountmanager",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_customers",
    )
    notes = models.TextField("opmerkingen / werkinstructies", blank=True)
    active = models.BooleanField("actief", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "klant"
        verbose_name_plural = "klanten"

    def __str__(self):
        return self.name

    @property
    def address(self):
        parts = [self.street, " ".join(p for p in [self.postal_code, self.city] if p), self.country]
        return ", ".join(p for p in parts if p)


class ShippingLine(TimeStampedModel):
    PROVIDER_CHOICES = [
        ("", "Standaard (instelling TRACKING_DEFAULT_PROVIDER)"),
        ("mock", "Demo / test (geen echte API)"),
        ("dcsa", "DCSA Track & Trace (REST)"),
        ("terminal49", "Terminal49 (alle rederijen via één API)"),
        ("safecube", "Safecube / Sinay (alle rederijen via één API)"),
        ("none", "Geen automatische tracking"),
    ]

    name = models.CharField("rederij", max_length=150, unique=True)
    scac = models.CharField("SCAC-code", max_length=4, blank=True, help_text="Bijv. MAEU, MSCU, CMDU, HLCU.")
    website = models.URLField("website", blank=True)
    contact_email = models.EmailField("contact e-mail", blank=True)
    contact_phone = models.CharField("contact telefoon", max_length=50, blank=True)
    tracking_provider = models.CharField("tracking provider", max_length=20, choices=PROVIDER_CHOICES, blank=True)
    api_base_url = models.URLField(
        "API base URL", blank=True, help_text="Bijv. https://api.rederij.com/track-and-trace/v2 (DCSA)."
    )
    api_key_env = models.CharField(
        "omgevingsvariabele met API-sleutel",
        max_length=100,
        blank=True,
        help_text="Naam van de environment variable waarin de API-sleutel staat (de sleutel zelf wordt niet in de database bewaard).",
    )
    api_key_header = models.CharField("header voor API-sleutel", max_length=60, default="Consumer-Key", blank=True)
    oauth_token_url = models.URLField(
        "OAuth2 token-URL", blank=True,
        help_text="Alleen nodig als de rederij OAuth2 (client credentials) gebruikt, bijv. Maersk of de private API van CMA CGM.",
    )
    oauth_client_id_env = models.CharField("omgevingsvariabele met client-ID", max_length=100, blank=True)
    oauth_client_secret_env = models.CharField("omgevingsvariabele met client-secret", max_length=100, blank=True)
    notes = models.TextField("opmerkingen", blank=True)
    active = models.BooleanField("actief", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "rederij"
        verbose_name_plural = "rederijen"

    def __str__(self):
        return f"{self.name} ({self.scac})" if self.scac else self.name


class RoadCarrier(TimeStampedModel):
    name = models.CharField("vervoerder", max_length=150, unique=True)
    contact_name = models.CharField("contactpersoon", max_length=150, blank=True)
    email = models.EmailField("e-mail", blank=True)
    phone = models.CharField("telefoon", max_length=50, blank=True)
    city = models.CharField("plaats", max_length=100, blank=True)
    country = models.CharField("land", max_length=100, blank=True)
    reefer_capable = models.BooleanField("koel/vries transport", default=True)
    adr_capable = models.BooleanField("ADR", default=False)
    notes = models.TextField("opmerkingen", blank=True)
    active = models.BooleanField("actief", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "vervoerder"
        verbose_name_plural = "vervoerders"

    def __str__(self):
        return self.name


class InspectionPoint(TimeStampedModel):
    TYPE_CHOICES = [
        ("gcp", "Grenscontrolepost (GCP/BCP)"),
        ("cp", "Controlepunt"),
        ("warehouse", "Koel-/vrieshuis met keurfaciliteit"),
        ("other", "Overig"),
    ]

    name = models.CharField("keurpunt", max_length=150, unique=True)
    point_type = models.CharField("type", max_length=20, choices=TYPE_CHOICES, default="gcp")
    traces_code = models.CharField("TRACES / BCP-code", max_length=40, blank=True, help_text="Bijv. NLRTM4.")
    street = models.CharField("adres", max_length=200, blank=True)
    city = models.CharField("plaats", max_length=100, blank=True)
    email = models.EmailField("e-mail", blank=True)
    phone = models.CharField("telefoon", max_length=50, blank=True)
    opening_hours = models.CharField("openingstijden", max_length=200, blank=True)
    handles_veterinary = models.BooleanField("veterinair (LNV/NVWA)", default=True)
    handles_phytosanitary = models.BooleanField("fytosanitair", default=False)
    notes = models.TextField("opmerkingen", blank=True)
    active = models.BooleanField("actief", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "keurpunt"
        verbose_name_plural = "keurpunten"

    def __str__(self):
        return self.name


class AuditLog(models.Model):
    """Wijzigingslog: wie heeft wat wanneer aangepast."""

    ACTION_CHOICES = [("create", "Aangemaakt"), ("update", "Gewijzigd"), ("delete", "Verwijderd"), ("event", "Gebeurtenis")]

    timestamp = models.DateTimeField("tijdstip", auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="gebruiker", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    action = models.CharField("actie", max_length=10, choices=ACTION_CHOICES)
    content_type = models.ForeignKey("contenttypes.ContentType", null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.CharField(max_length=40, blank=True, db_index=True)
    object_repr = models.CharField("object", max_length=250)
    changes = models.JSONField("wijzigingen", default=dict, blank=True)
    message = models.CharField("toelichting", max_length=300, blank=True)

    class Meta:
        ordering = ["-timestamp", "-id"]
        verbose_name = "logregel"
        verbose_name_plural = "wijzigingslog"
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return f"{self.get_action_display()} {self.object_repr}"

    @property
    def type_label(self):
        model = self.content_type.model_class() if self.content_type_id else None
        return model._meta.verbose_name if model else ""


class NotificationPreference(models.Model):
    SCOPE_CHOICES = [("mine", "Alleen dossiers waar ik behandelaar ben"), ("all", "Alle dossiers")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_prefs")
    shipment_scope = models.CharField("zendingmeldingen voor", max_length=10, choices=SCOPE_CHOICES, default="mine")
    vessel_change = models.BooleanField("container van schip gewisseld", default=True)
    eta_change = models.BooleanField("ETA verschoven", default=True)
    eta_threshold_hours = models.PositiveSmallIntegerField("ETA-melding vanaf (uur verschuiving)", default=12)
    action_assigned = models.BooleanField("actie aan mij toegewezen", default=True)
    escalations = models.BooleanField("nieuwe escalaties / niveau omhoog", default=False)
    daily_digest = models.BooleanField("dagelijks overzicht ('s ochtends)", default=True)
    shift_reminder = models.BooleanField("herinnering dag vóór mijn dienst", default=True)
    swap_requests = models.BooleanField("ruilverzoeken diensten", default=True)

    class Meta:
        verbose_name = "meldingsvoorkeur"
        verbose_name_plural = "meldingsvoorkeuren"

    def __str__(self):
        return f"Meldingen {self.user}"

    @classmethod
    def for_user(cls, user):
        prefs, _ = cls.objects.get_or_create(user=user)
        return prefs


class JobRun(models.Model):
    """Laatste uitvoering van geplande taken (voorkomt dubbele dagoverzichten na een herstart)."""

    name = models.CharField(max_length=50, unique=True)
    last_run = models.DateTimeField()

    def __str__(self):
        return f"{self.name}: {self.last_run}"


class UserProfile(models.Model):
    """Extra accountinformatie. Een account met een klant is een klantportaal-account."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    customer = models.ForeignKey(
        Customer, verbose_name="klant (klantportaal)", null=True, blank=True, on_delete=models.CASCADE, related_name="portal_users"
    )

    class Meta:
        verbose_name = "accountprofiel"
        verbose_name_plural = "accountprofielen"

    def __str__(self):
        return f"Profiel {self.user}"


def portal_customer(user):
    """De klant van een klantportaal-account, of None voor interne medewerkers."""
    profile = getattr(user, "profile", None) if user is not None and user.is_authenticated else None
    return profile.customer if profile is not None else None
