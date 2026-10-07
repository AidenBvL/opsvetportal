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
    tracking_url_template = models.CharField(
        "link naar trackingpagina", max_length=300, blank=True,
        help_text="Bijv. https://www.rederij.com/track?ref={number}. {container} = containernummer, {number} = B/L of boeking.",
    )
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


class Port(TimeStampedModel):
    """Zeehaven met UN/LOCODE. Dossiers slaan de code op; namen uit B/L's en trackingpagina's worden omgezet."""

    locode = models.CharField("UN/LOCODE", max_length=5, unique=True, help_text="Bijv. NLRTM (landcode + 3 tekens).")
    name = models.CharField("naam", max_length=100)
    aliases = models.CharField(
        "andere schrijfwijzen", max_length=300, blank=True,
        help_text="Komma-gescheiden namen zoals ze op B/L's of trackingpagina's staan, bijv. ANTWERP, ANVERS.",
    )
    container_port = models.BooleanField(
        "containerhaven", default=False,
        help_text="Komt in de suggesties en gaat voor bij havens met dezelfde naam (bijv. Manzanillo).",
    )
    active = models.BooleanField("actief", default=True)

    class Meta:
        ordering = ["locode"]
        verbose_name = "haven"
        verbose_name_plural = "havens"

    def __str__(self):
        return f"{self.name} ({self.locode})"

    @property
    def country(self):
        return self.locode[:2]

    @property
    def country_name(self):
        from .data.countries import COUNTRY_NAMES

        return COUNTRY_NAMES.get(self.country, self.country)

    def save(self, *args, **kwargs):
        from .ports import clear_cache, recode_shipments

        self.locode = self.locode.replace(" ", "").upper()
        super().save(*args, **kwargs)
        clear_cache()
        recode_shipments()

    def delete(self, *args, **kwargs):
        from .ports import clear_cache

        result = super().delete(*args, **kwargs)
        clear_cache()
        return result


class Terminal(TimeStampedModel):
    """Containerterminal. Varianten uit tracking ("ECT EUROMAX ROTTERDAM") worden de volledige naam."""

    name = models.CharField("volledige naam", max_length=150)
    code = models.CharField("terminalcode (SMDG)", max_length=10, blank=True, help_text="Bijv. EMX voor ECT Euromax.")
    port = models.ForeignKey(Port, verbose_name="haven", null=True, blank=True, on_delete=models.SET_NULL, related_name="terminals")
    company = models.CharField("bedrijf", max_length=150, blank=True)
    address = models.CharField("adres", max_length=250, blank=True)
    website = models.URLField("website", max_length=250, blank=True)
    aliases = models.CharField(
        "andere schrijfwijzen", max_length=400, blank=True,
        help_text="Komma-gescheiden, zoals rederijen en trackingdiensten de terminal noemen, bijv. ECT EUROMAX ROTTERDAM, EUROMAX.",
    )
    active = models.BooleanField("actief", default=True)

    class Meta:
        ordering = ["port__locode", "name"]
        verbose_name = "terminal"
        verbose_name_plural = "terminals"
        constraints = [
            models.UniqueConstraint(fields=["port", "code"], condition=~models.Q(code=""), name="unique_terminal_code_per_port"),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})" if self.code and f"({self.code})" not in self.name else self.name

    @property
    def country_name(self):
        return self.port.country_name if self.port_id else ""

    @property
    def label(self):
        """"ECT EUROMAX TERMINAL (EMX) · Rotterdam, Nederland (NLRTM)"."""
        from .ports import port_label

        return f"{self} · {port_label(self.port.locode)}" if self.port_id else str(self)

    def save(self, *args, **kwargs):
        from .ports import clear_cache, recode_shipments

        super().save(*args, **kwargs)
        clear_cache()
        recode_shipments()

    def delete(self, *args, **kwargs):
        from .ports import clear_cache

        result = super().delete(*args, **kwargs)
        clear_cache()
        return result


class Address(TimeStampedModel):
    """Laad- of losadres voor wegtransport, met de vaste afspraken (tijden, aanmelden, instructies)."""

    KIND_CHOICES = [("los", "Losadres"), ("laad", "Laadadres"), ("beide", "Laad- en losadres")]

    name = models.CharField("naam", max_length=100, help_text="Korte naam om te kiezen, bijv. 'Ter Maten Bunschoten'.")
    customer = models.ForeignKey(
        Customer, verbose_name="klant", null=True, blank=True, on_delete=models.CASCADE, related_name="addresses",
        help_text="Leeg laten voor een adres dat voor meerdere klanten gebruikt wordt (bijv. een koelhuis).",
    )
    kind = models.CharField("soort", max_length=10, choices=KIND_CHOICES, default="los")
    is_default = models.BooleanField("standaard losadres van deze klant", default=False)
    company = models.CharField("bedrijfsnaam", max_length=150, blank=True)
    street = models.CharField("straat + huisnummer", max_length=150, blank=True)
    postal_code = models.CharField("postcode", max_length=20, blank=True)
    city = models.CharField("plaats", max_length=100)
    country = models.CharField("land", max_length=100, default="Nederland")
    contact_name = models.CharField("contactpersoon", max_length=100, blank=True)
    phone = models.CharField("telefoon", max_length=50, blank=True)
    email = models.EmailField("e-mail", blank=True)
    opening_hours = models.CharField("ontvangsttijden", max_length=200, blank=True, help_text="Bijv. ma-vr 06:00-15:00.")
    booking_required = models.BooleanField("tijdslot / vooraanmelding verplicht", default=False)
    instructions = models.TextField(
        "instructies voor de chauffeur", blank=True, help_text="Bijv. melden bij portier, dock 4, max. 13,6 m, pallets ruilen.",
    )
    active = models.BooleanField("actief", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "adres"
        verbose_name_plural = "adressen"

    def __str__(self):
        return f"{self.name} ({self.city})" if self.city and self.city.lower() not in self.name.lower() else self.name

    @property
    def lines(self):
        return [line for line in [self.company, self.street, " ".join(p for p in [self.postal_code, self.city] if p), self.country] if line]

    @property
    def one_line(self):
        return ", ".join(self.lines)

    @property
    def maps_url(self):
        from urllib.parse import quote

        return "https://www.google.com/maps/search/?api=1&query=" + quote(", ".join(self.lines[1:] or self.lines))

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default and self.customer_id:
            # Eén standaard losadres per klant.
            Address.objects.filter(customer_id=self.customer_id, is_default=True).exclude(pk=self.pk).update(is_default=False)


class ListPreference(models.Model):
    """Welke kolommen iemand in een lijst ziet, en in welke volgorde."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="list_preferences")
    key = models.CharField(max_length=40)
    columns = models.JSONField(default=list)
    compact = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "key"], name="unique_list_preference")]
        verbose_name = "lijstweergave"
        verbose_name_plural = "lijstweergaven"

    def __str__(self):
        return f"{self.user} · {self.key}"


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
