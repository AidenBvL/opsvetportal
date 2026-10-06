from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import generic
from django.views.decorators.http import require_POST

from actions.models import Action
from planning.models import Shift, WorkFromHomeDay

from .forms import MeetingBlockForm, MeetingItemForm, QuickItemForm
from .models import MeetingBlock, MeetingItem


def _day(request):
    try:
        return date.fromisoformat(request.GET.get("datum") or timezone.localdate().isoformat())
    except ValueError as exc:
        raise Http404 from exc


def day_url(day):
    return f"{reverse('meetings:day')}?datum={day.isoformat()}"


class DayView(PermissionRequiredMixin, generic.TemplateView):
    permission_required = "meetings.view_meetingitem"
    template_name = "meetings/day.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        day = _day(self.request)
        existing = {b.block: b for b in MeetingBlock.objects.filter(date=day).prefetch_related(
            "attendees", "items__colleagues", "items__raised_by", "items__customer", "items__sea_shipment", "items__actions")}
        blocks = []
        for key in MeetingBlock.BLOCK_ORDER:
            block = existing.get(key)
            blocks.append({
                "key": key,
                "label": dict(MeetingBlock.BLOCK_CHOICES)[key],
                "obj": block,
                "items": list(block.items.all()) if block else [],
                "form": QuickItemForm(prefix=key),
                "block_form": MeetingBlockForm(instance=block, prefix=f"b-{key}"),
            })
        prev_day = day - timedelta(days=1)
        while prev_day.weekday() >= 5:
            prev_day -= timedelta(days=1)
        next_day = day + timedelta(days=1)
        while next_day.weekday() >= 5:
            next_day += timedelta(days=1)
        context.update({
            "day": day, "blocks": blocks, "prev_day": prev_day, "next_day": next_day,
            "today": timezone.localdate(),
            "open_elsewhere": MeetingItem.objects.filter(status="open", meeting__date__lt=day,
                                                         meeting__date__gte=day - timedelta(days=14)).select_related("meeting")[:20],
            "wfh": WorkFromHomeDay.objects.filter(date=day).select_related("employee"),
            "shift": Shift.objects.filter(date=day).select_related("employee").first(),
            "can_add": self.request.user.has_perm("meetings.add_meetingitem"),
        })
        return context


@require_POST
@permission_required("meetings.add_meetingitem", raise_exception=True)
def add_item(request):
    day = date.fromisoformat(request.POST["datum"])
    key = request.POST["block"]
    if key not in MeetingBlock.BLOCK_ORDER:
        raise Http404
    form = QuickItemForm(request.POST, prefix=key)
    if form.is_valid():
        block, _ = MeetingBlock.objects.get_or_create(date=day, block=key)
        item = form.save(commit=False)
        item.meeting = block
        item.created_by = request.user
        item.save()
        form.save_m2m()
        messages.success(request, "Punt toegevoegd.")
    else:
        messages.error(request, "Vul minimaal de vraag / het onderwerp in.")
    return redirect(day_url(day) + f"#{key}")


@require_POST
@permission_required("meetings.change_meetingblock", raise_exception=True)
def save_block(request):
    day = date.fromisoformat(request.POST["datum"])
    key = request.POST["block"]
    block, _ = MeetingBlock.objects.get_or_create(date=day, block=key)
    form = MeetingBlockForm(request.POST, instance=block, prefix=f"b-{key}")
    if form.is_valid():
        form.save()
        messages.success(request, f"{block.get_block_display()} opgeslagen.")
    return redirect(day_url(day) + f"#{key}")


class ItemUpdateView(PermissionRequiredMixin, generic.UpdateView):
    permission_required = "meetings.change_meetingitem"
    model = MeetingItem
    form_class = MeetingItemForm
    template_name = "meetings/item_form.html"

    def get_success_url(self):
        return day_url(self.object.meeting.date) + f"#{self.object.meeting.block}"


def next_block(day, key):
    index = MeetingBlock.BLOCK_ORDER.index(key)
    if index + 1 < len(MeetingBlock.BLOCK_ORDER):
        return day, MeetingBlock.BLOCK_ORDER[index + 1]
    nxt = day + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt, MeetingBlock.BLOCK_ORDER[0]


@require_POST
@permission_required("meetings.change_meetingitem", raise_exception=True)
def item_action(request, pk):
    item = get_object_or_404(MeetingItem.objects.select_related("meeting"), pk=pk)
    action = request.POST.get("action")
    day = item.meeting.date
    if action == "answered":
        item.status = "beantwoord"
        if request.POST.get("answer"):
            item.answer = request.POST["answer"]
        item.save()
    elif action == "reopen":
        item.status = "open"
        item.save()
    elif action == "carry":
        new_day, new_key = next_block(day, item.meeting.block)
        block, _ = MeetingBlock.objects.get_or_create(date=new_day, block=new_key)
        copy = MeetingItem.objects.create(
            meeting=block, title=item.title, details=item.details, raised_by=item.raised_by, customer=item.customer,
            sea_shipment=item.sea_shipment, road_transport=item.road_transport, carried_from=item, created_by=request.user,
        )
        copy.colleagues.set(item.colleagues.all())
        item.status = "doorgeschoven"
        item.save()
        messages.success(request, f"Doorgeschoven naar {block}.")
    elif action in ("to_action", "to_escalation"):
        if not request.user.has_perm("actions.add_action"):
            raise Http404
        new = Action.objects.create(
            title=item.title, description=item.details,
            kind=Action.KIND_ESCALATION if action == "to_escalation" else Action.KIND_ACTION,
            owner=item.colleagues.first() or item.raised_by, customer=item.customer, sea_shipment=item.sea_shipment,
            road_transport=item.road_transport, meeting_item=item, created_by=request.user,
            due_date=timezone.localdate() + timedelta(days=1),
        )
        messages.success(request, f"{new.get_kind_display()} aangemaakt.")
        return redirect("actions:action_update", pk=new.pk)
    elif action == "delete" and request.user.has_perm("meetings.delete_meetingitem"):
        item.delete()
    return redirect(day_url(day) + f"#{item.meeting.block}")


class OpenItemsView(PermissionRequiredMixin, generic.ListView):
    permission_required = "meetings.view_meetingitem"
    template_name = "meetings/open_items.html"
    paginate_by = 50

    def get_queryset(self):
        qs = MeetingItem.objects.filter(status="open").select_related("meeting", "raised_by", "customer").prefetch_related("colleagues")
        employee = self.request.GET.get("collega")
        if employee:
            qs = qs.filter(colleagues__id=employee)
        return qs.order_by("meeting__date", "meeting__block")

    def get_context_data(self, **kwargs):
        from planning.models import Employee

        context = super().get_context_data(**kwargs)
        context["employees"] = Employee.objects.filter(active=True)
        context["selected"] = self.request.GET.get("collega", "")
        return context
