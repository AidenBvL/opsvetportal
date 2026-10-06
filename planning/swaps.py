"""Ruilverzoeken: aanvrager → collega accepteert → planner keurt goed → rooster wordt aangepast."""

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q

from core import notifications

from . import services
from .models import Shift, ShiftSwapRequest, WorkFromHomeDay


class SwapError(Exception):
    pass


def planners():
    return User.objects.filter(is_active=True).filter(
        Q(is_superuser=True) | Q(user_permissions__codename="generate_roster") | Q(groups__permissions__codename="generate_roster")
    ).distinct()


def _user(employee):
    return getattr(employee, "user", None)


def preview_issues(swap):
    """Spelregelwaarschuwingen als de ruil zou worden doorgevoerd (zonder iets op te slaan)."""
    issues = []
    test = Shift(pk=swap.shift.pk, date=swap.shift.date, shift_type=swap.shift.shift_type, employee=swap.colleague)
    issues += services.validate_shift(test)
    if swap.colleague_shift:
        back = Shift(pk=swap.colleague_shift.pk, date=swap.colleague_shift.date,
                     shift_type=swap.colleague_shift.shift_type, employee=swap.requester)
        issues += services.validate_shift(back)
    return issues


def create(shift, requester, colleague, colleague_shift=None, message=""):
    if shift.employee_id != requester.id:
        raise SwapError("Je kunt alleen je eigen diensten ruilen.")
    if colleague.id == requester.id:
        raise SwapError("Kies een collega.")
    if colleague_shift and colleague_shift.employee_id != colleague.id:
        raise SwapError("De gekozen ruildienst is niet van deze collega.")
    if ShiftSwapRequest.objects.filter(shift=shift, status__in=ShiftSwapRequest.OPEN_STATUSES).exists():
        raise SwapError("Voor deze dienst loopt al een ruilverzoek.")
    swap = ShiftSwapRequest.objects.create(shift=shift, requester=requester, colleague=colleague,
                                           colleague_shift=colleague_shift, message=message)
    notifications.swap_event(swap, [_user(colleague)], f"Ruilverzoek van {requester.first_name}: {shift.date:%d-%m}")
    return swap


def respond(swap, employee, accept):
    if not swap.status == ShiftSwapRequest.STATUS_WAIT_COLLEAGUE or employee != swap.colleague:
        raise SwapError("Dit verzoek wacht niet op jouw reactie.")
    swap.status = ShiftSwapRequest.STATUS_WAIT_PLANNER if accept else ShiftSwapRequest.STATUS_DECLINED
    swap.save()
    if accept:
        notifications.swap_event(swap, list(planners()), f"Ruil ter goedkeuring: {swap.shift.date:%d-%m} {swap.requester.first_name} → {swap.colleague.first_name}")
    notifications.swap_event(swap, [_user(swap.requester)], f"Ruilverzoek {swap.shift.date:%d-%m} {'geaccepteerd' if accept else 'geweigerd'} door {swap.colleague.first_name}")


def cancel(swap, employee):
    if not swap.is_open or employee != swap.requester:
        raise SwapError("Je kunt dit verzoek niet intrekken.")
    swap.status = ShiftSwapRequest.STATUS_CANCELLED
    swap.save()


@transaction.atomic
def decide(swap, user, approve, note=""):
    if swap.status != ShiftSwapRequest.STATUS_WAIT_PLANNER:
        raise SwapError("Dit verzoek wacht niet op goedkeuring.")
    swap.decided_by = user
    swap.decision_note = note
    if approve:
        shift = Shift.objects.select_for_update().get(pk=swap.shift_id)
        if shift.employee_id != swap.requester_id:
            raise SwapError("De dienst is inmiddels aan iemand anders toegewezen.")
        moves = [(shift, swap.colleague)]
        if swap.colleague_shift_id:
            other = Shift.objects.select_for_update().get(pk=swap.colleague_shift_id)
            if other.employee_id != swap.colleague_id:
                raise SwapError("De ruildienst van de collega is inmiddels gewijzigd.")
            moves.append((other, swap.requester))
        for s, employee in moves:
            s.employee = employee
            s.is_manual = True
            s.linked_to_wfh = WorkFromHomeDay.objects.filter(employee=employee, date=s.date).exists()
            s.note = f"Ruil goedgekeurd door {user.get_full_name() or user.username}"
            s.save()
        swap.status = ShiftSwapRequest.STATUS_APPROVED
    else:
        swap.status = ShiftSwapRequest.STATUS_REJECTED
    swap.save()
    notifications.swap_event(swap, [_user(swap.requester), _user(swap.colleague)],
                             f"Ruil {swap.shift.date:%d-%m} {'goedgekeurd' if approve else 'afgewezen'}")
    return swap
