from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.auth.models import Group, User
from django.db.models import Count, Q, Sum
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import generic

from actions.models import Action, ExtraCost
from meetings.models import MeetingItem
from planning.models import Shift, WorkFromHomeDay
from shipments.models import RoadTransport, SeaShipment, TrackingUpdate

from .forms import GroupForm, UserForm
from .models import Customer


def cost_summary(queryset):
    totals = {key: Decimal("0") for key, _ in ExtraCost.RESPONSIBILITY_CHOICES}
    for row in queryset.values("responsibility").annotate(total=Sum("amount")):
        totals[row["responsibility"]] = row["total"] or Decimal("0")
    labels = dict(ExtraCost.RESPONSIBILITY_CHOICES)
    return [{"key": k, "label": labels[k], "total": v} for k, v in totals.items()]


class DashboardView(generic.TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        now = timezone.now()
        open_actions = Action.objects.filter(status__in=Action.OPEN_STATUSES).select_related("owner", "customer")
        employee = getattr(self.request.user, "employee", None)
        context.update(
            {
                "today": today,
                "employee": employee,
                "shifts_today": Shift.objects.filter(date=today).select_related("employee"),
                "shifts_upcoming": Shift.objects.filter(date__gt=today, date__lte=today + timedelta(days=6)).select_related("employee"),
                "wfh_today": WorkFromHomeDay.objects.filter(date=today).select_related("employee"),
                "my_shifts": Shift.objects.filter(employee=employee, date__gte=today)[:5] if employee else [],
                "open_actions_count": open_actions.filter(kind=Action.KIND_ACTION).count(),
                "escalations": open_actions.filter(kind=Action.KIND_ESCALATION).order_by("-escalation_level", "-priority")[:8],
                "escalations_count": open_actions.filter(kind=Action.KIND_ESCALATION).count(),
                "overdue": open_actions.filter(due_date__lt=today).order_by("due_date")[:8],
                "my_actions": open_actions.filter(owner=employee)[:8] if employee else [],
                "arrivals": SeaShipment.objects.filter(
                    status__in=SeaShipment.OPEN_STATUSES, eta__date__range=(today - timedelta(days=1), today + timedelta(days=7))
                ).select_related("customer", "shipping_line", "inspection_point").order_by("eta")[:15],
                "vessel_changes": SeaShipment.objects.filter(vessel_changed=True, status__in=SeaShipment.OPEN_STATUSES).select_related("customer")[:10],
                "inspection_todo": SeaShipment.objects.filter(
                    inspection_required=True, status__in=SeaShipment.OPEN_STATUSES, inspection_status="aan_te_melden"
                ).count(),
                "demurrage_risk": [s for s in SeaShipment.objects.filter(status__in=SeaShipment.OPEN_STATUSES, free_time_until__isnull=False).select_related("customer") if s.demurrage_risk][:10],
                "road_today": RoadTransport.objects.filter(
                    Q(loading_at__date=today) | Q(delivery_planned_at__date=today)
                ).select_related("customer", "carrier"),
                "open_questions": MeetingItem.objects.filter(status="open", meeting__date__gte=today - timedelta(days=7)).count(),
                "recent_tracking": TrackingUpdate.objects.filter(checked_at__gte=now - timedelta(days=2)).exclude(message="").select_related("shipment")[:8],
                "cost_totals": cost_summary(ExtraCost.objects.filter(cost_date__gte=today.replace(day=1))),
            }
        )
        return context


class CustomerDetailView(PermissionRequiredMixin, generic.DetailView):
    model = Customer
    permission_required = "core.view_customer"
    template_name = "core/customer_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        c = self.object
        costs = ExtraCost.objects.filter(customer=c)
        context.update(
            {
                "sea_open": c.sea_shipments.filter(status__in=SeaShipment.OPEN_STATUSES).select_related("shipping_line", "inspection_point"),
                "sea_closed_count": c.sea_shipments.exclude(status__in=SeaShipment.OPEN_STATUSES).count(),
                "road_open": c.road_transports.filter(status__in=RoadTransport.OPEN_STATUSES).select_related("carrier"),
                "actions": c.actions.filter(status__in=Action.OPEN_STATUSES).select_related("owner"),
                "costs": costs.select_related("action")[:20],
                "cost_totals": cost_summary(costs),
                "documents": c.documents.all()[:10],
            }
        )
        return context


# --- Accounts & rechten ------------------------------------------------------


class UserListView(PermissionRequiredMixin, generic.ListView):
    permission_required = "auth.view_user"
    template_name = "core/user_list.html"
    queryset = User.objects.order_by("username").prefetch_related("groups").select_related("employee")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["groups"] = Group.objects.annotate(n_users=Count("user"), n_perms=Count("permissions", distinct=True))
        return context


class UserFormMixin(PermissionRequiredMixin):
    model = User
    form_class = UserForm
    template_name = "core/user_form.html"
    success_url = reverse_lazy("core:user_list")

    def form_valid(self, form):
        messages.success(self.request, f"Account {form.instance.username} opgeslagen.")
        return super().form_valid(form)


class UserCreateView(UserFormMixin, generic.CreateView):
    permission_required = "auth.add_user"


class UserUpdateView(UserFormMixin, generic.UpdateView):
    permission_required = "auth.change_user"


class GroupFormMixin(PermissionRequiredMixin):
    model = Group
    form_class = GroupForm
    template_name = "core/group_form.html"
    success_url = reverse_lazy("core:user_list")


class GroupCreateView(GroupFormMixin, generic.CreateView):
    permission_required = "auth.add_group"


class GroupUpdateView(GroupFormMixin, generic.UpdateView):
    permission_required = "auth.change_group"
