import uuid

from django.conf import settings
from django.db import models

from core.fields import WeekdaysField, weekdays_label
from core.models import TimeStampedModel


class Department(models.Model):
    name = models.CharField("afdeling / groep", max_length=100, unique=True)
    description = models.CharField("omschrijving", max_length=200, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "afdeling"
        verbose_name_plural = "afdelingen"

    def __str__(self):
        return self.name


class Employee(TimeStampedModel):
    name = models.CharField("naam", max_length=150, unique=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="gekoppeld account",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employee",
    )
    job_title = models.CharField("functie", max_length=150, blank=True)
    departments = models.ManyToManyField(
        Department,
        verbose_name="afdelingsgroepen",
        blank=True,
        related_name="employees",
        help_text="Collega's uit dezelfde groep werken nooit op dezelfde of direct opvolgende dag thuis.",
    )
    email = models.EmailField("e-mail", blank=True)
    phone = models.CharField("telefoon", max_length=50, blank=True)
    active = models.BooleanField("actief", default=True)

    # Thuiswerken
    wfh_days_per_week = models.PositiveSmallIntegerField(
        "thuiswerkdagen per week", default=1, help_text="0 = neemt niet deel aan het thuiswerkschema."
    )
    preferred_wfh_weekdays = WeekdaysField(
        "voorkeur thuiswerkdag(en)", help_text="Optioneel; de generator probeert deze dagen te gebruiken."
    )
    days_off = WeekdaysField("vaste vrije dag(en)", help_text="Bijv. woensdag bij een 4-daagse werkweek.")

    # Diensten
    in_shift_pool = models.BooleanField("draait avond-/zaterdagdiensten", default=True)
    no_shift_weekdays = WeekdaysField(
        "geen dienst op", help_text="Weekdagen waarop deze persoon nooit dienst krijgt (bijv. schooldag)."
    )

    calendar_token = models.UUIDField("agenda-token", default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "medewerker"
        verbose_name_plural = "medewerkers"

    def __str__(self):
        return self.name

    @property
    def first_name(self):
        return self.name.split(" ")[0]

    @property
    def days_off_label(self):
        return weekdays_label(self.days_off)

    @property
    def no_shift_label(self):
        return weekdays_label(self.no_shift_weekdays)


class Absence(TimeStampedModel):
    REASON_CHOICES = [
        ("vakantie", "Vakantie / verlof"),
        ("ziek", "Ziek"),
        ("school", "School / opleiding"),
        ("overig", "Overig"),
    ]
    employee = models.ForeignKey(Employee, verbose_name="medewerker", on_delete=models.CASCADE, related_name="absences")
    start_date = models.DateField("van")
    end_date = models.DateField("t/m")
    reason = models.CharField("reden", max_length=20, choices=REASON_CHOICES, default="vakantie")
    note = models.CharField("toelichting", max_length=200, blank=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "afwezigheid"
        verbose_name_plural = "afwezigheden"

    def __str__(self):
        return f"{self.employee} {self.start_date:%d-%m} t/m {self.end_date:%d-%m} ({self.get_reason_display()})"


class Holiday(models.Model):
    date = models.DateField("datum", unique=True)
    name = models.CharField("feestdag", max_length=100)

    class Meta:
        ordering = ["date"]
        verbose_name = "feestdag"
        verbose_name_plural = "feestdagen"

    def __str__(self):
        return f"{self.name} ({self.date:%d-%m-%Y})"


class RosterMonth(TimeStampedModel):
    STATUS_CHOICES = [("concept", "Concept"), ("definitief", "Definitief")]

    year = models.PositiveSmallIntegerField("jaar")
    month = models.PositiveSmallIntegerField("maand")
    status = models.CharField("status", max_length=20, choices=STATUS_CHOICES, default="concept")
    generated_at = models.DateTimeField("gegenereerd op", null=True, blank=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    notes = models.TextField("opmerkingen / meldingen generator", blank=True)

    class Meta:
        ordering = ["-year", "-month"]
        unique_together = [("year", "month")]
        verbose_name = "roostermaand"
        verbose_name_plural = "roostermaanden"
        permissions = [("generate_roster", "Mag rooster genereren en vaststellen")]

    def __str__(self):
        return f"{self.month:02d}-{self.year}"


class WorkFromHomeDay(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="wfh_days", verbose_name="medewerker")
    date = models.DateField("datum")
    is_manual = models.BooleanField("handmatig", default=False, help_text="Handmatige wijzigingen blijven staan bij hergenereren.")

    class Meta:
        ordering = ["date", "employee__name"]
        unique_together = [("employee", "date")]
        verbose_name = "thuiswerkdag"
        verbose_name_plural = "thuiswerkdagen"

    def __str__(self):
        return f"{self.employee} thuis op {self.date:%d-%m-%Y}"


class Shift(models.Model):
    EVENING = "avond"
    SATURDAY = "zaterdag"
    TYPE_CHOICES = [(EVENING, "Avonddienst"), (SATURDAY, "Zaterdagdienst")]

    date = models.DateField("datum")
    shift_type = models.CharField("type dienst", max_length=20, choices=TYPE_CHOICES)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="shifts", verbose_name="medewerker")
    linked_to_wfh = models.BooleanField("gekoppeld aan thuiswerk", default=False)
    is_manual = models.BooleanField("handmatig", default=False, help_text="Handmatige wijzigingen blijven staan bij hergenereren.")
    note = models.CharField("opmerking", max_length=200, blank=True)

    class Meta:
        ordering = ["date"]
        unique_together = [("date", "shift_type")]
        verbose_name = "dienst"
        verbose_name_plural = "diensten"

    def __str__(self):
        return f"{self.get_shift_type_display()} {self.date:%d-%m-%Y}: {self.employee}"
