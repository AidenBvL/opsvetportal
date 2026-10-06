"""Koppeling tussen de roostergenerator en de database."""

import calendar
from collections import Counter, defaultdict
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import generator
from .models import Absence, Employee, Holiday, RosterMonth, Shift, WorkFromHomeDay

HISTORY_DAYS = 120


class RosterLocked(Exception):
    pass


def month_bounds(year, month):
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def build_people(start, end):
    employees = Employee.objects.filter(active=True).prefetch_related("departments")
    absences = defaultdict(set)
    for absence in Absence.objects.filter(start_date__lte=end, end_date__gte=start):
        day = max(absence.start_date, start)
        while day <= min(absence.end_date, end):
            absences[absence.employee_id].add(day)
            day += timedelta(days=1)
    people = []
    for e in employees:
        people.append(
            generator.Person(
                id=e.id,
                name=e.name,
                groups=frozenset(d.name for d in e.departments.all()),
                wfh_days=e.wfh_days_per_week,
                preferred_wfh=frozenset(e.preferred_wfh_weekdays),
                days_off=frozenset(e.days_off),
                in_pool=e.in_shift_pool,
                no_shift_weekdays=frozenset(e.no_shift_weekdays),
                unavailable=frozenset(absences[e.id]),
            )
        )
    return people


def previous_wfh_pattern(start):
    """Leid het weekpatroon af uit de thuiswerkdagen van de voorgaande maand."""
    prev_end = start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    counts = defaultdict(Counter)
    for wfh in WorkFromHomeDay.objects.filter(date__range=(prev_start, prev_end)).select_related("employee"):
        counts[wfh.employee_id][wfh.date.weekday()] += 1
    pattern = {}
    for employee in Employee.objects.filter(id__in=counts):
        top = [d for d, _ in counts[employee.id].most_common(employee.wfh_days_per_week)]
        pattern[employee.id] = frozenset(top)
    return pattern


@transaction.atomic
def generate_month(year, month, user=None, force=False):
    roster, _ = RosterMonth.objects.get_or_create(year=year, month=month)
    if roster.status == "definitief" and not force:
        raise RosterLocked("Dit rooster is definitief vastgesteld. Zet het eerst terug naar concept.")

    start, end = month_bounds(year, month)
    holidays = set(Holiday.objects.filter(date__range=(start, end)).values_list("date", flat=True))
    people = build_people(start, end)

    history = {}
    window = Shift.objects.filter(date__range=(start - timedelta(days=HISTORY_DAYS), end + timedelta(days=7)))
    window = window.filter(Q(date__lt=start) | Q(date__gt=end) | Q(is_manual=True))
    for shift in window:
        history[(shift.date, shift.shift_type)] = shift.employee_id

    fixed_wfh = defaultdict(set)
    for wfh in WorkFromHomeDay.objects.filter(date__range=(start, end), is_manual=True):
        fixed_wfh[wfh.date].add(wfh.employee_id)

    result = generator.generate(
        people,
        start,
        end,
        history=history,
        holidays=holidays,
        previous_pattern=previous_wfh_pattern(start),
        fixed_wfh=fixed_wfh,
    )

    WorkFromHomeDay.objects.filter(date__range=(start, end), is_manual=False).delete()
    Shift.objects.filter(date__range=(start, end), is_manual=False).delete()

    WorkFromHomeDay.objects.bulk_create(
        [
            WorkFromHomeDay(employee_id=pid, date=day)
            for day, pids in result.wfh.items()
            for pid in pids
            if pid not in fixed_wfh.get(day, ())
        ]
    )
    Shift.objects.bulk_create(
        [
            Shift(date=day, shift_type=kind, employee_id=pid, linked_to_wfh=pid in result.wfh.get(day, ()))
            for (day, kind), pid in result.shifts.items()
            if pid is not None
        ]
    )
    refresh_wfh_links(start, end)

    roster.generated_at = timezone.now()
    roster.generated_by = user if user and user.is_authenticated else None
    roster.notes = "\n".join(result.warnings)
    roster.save()
    from core.audit import log_event

    log_event(roster, f"Rooster {month:02d}-{year} automatisch gegenereerd", user=roster.generated_by)
    return roster, result


def refresh_wfh_links(start, end):
    wfh = set(WorkFromHomeDay.objects.filter(date__range=(start, end)).values_list("employee_id", "date"))
    for shift in Shift.objects.filter(date__range=(start, end)):
        linked = (shift.employee_id, shift.date) in wfh
        if linked != shift.linked_to_wfh:
            shift.linked_to_wfh = linked
            shift.save(update_fields=["linked_to_wfh"])


def validate_shift(shift):
    """Controleer een (handmatig gewijzigde) dienst tegen de spelregels. Geeft waarschuwingen terug."""
    issues = []
    e = shift.employee
    day = shift.date
    if not e.in_shift_pool:
        issues.append(f"{e} staat niet in de dienstenpool.")
    if day.weekday() in e.no_shift_weekdays:
        issues.append(f"{e} heeft nooit dienst op deze weekdag.")
    if day.weekday() in e.days_off:
        issues.append(f"{e} is vrij op deze weekdag.")
    if Absence.objects.filter(employee=e, start_date__lte=day, end_date__gte=day).exists():
        issues.append(f"{e} is afwezig op {day:%d-%m-%Y}.")
    neighbours = Shift.objects.filter(
        employee=e, date__in=[day - timedelta(days=1), day + timedelta(days=1)]
    ).exclude(pk=shift.pk)
    if neighbours.exists():
        issues.append(f"{e} heeft ook dienst op een aangrenzende dag.")
    monday = day - timedelta(days=day.weekday())
    if shift.shift_type == Shift.SATURDAY:
        if Shift.objects.filter(employee=e, shift_type=Shift.EVENING, date__range=(monday, monday + timedelta(days=4))).exists():
            issues.append(f"{e} heeft deze week al een avonddienst en kan daarom geen zaterdagdienst draaien.")
    else:
        if Shift.objects.filter(employee=e, shift_type=Shift.SATURDAY, date=monday + timedelta(days=5)).exists():
            issues.append(f"{e} heeft zaterdag dienst; dan geen avonddienst in dezelfde week.")
    return issues
