import csv
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import generic
from django.views.decorators.http import require_POST

from core.crud import CrudCreateView, CrudListView, CrudUpdateView
from core.models import Customer
from core.views import cost_summary
from planning.models import Employee

from .forms import InlineCostForm
from .models import Action, ExtraCost


def filter_actions(request, qs):
    params = request.GET
    if params.get("soort"):
        qs = qs.filter(kind=params["soort"])
    if params.get("eigenaar"):
        qs = qs.filter(owner_id=params["eigenaar"])
    if params.get("klant"):
        qs = qs.filter(customer_id=params["klant"])
    if params.get("q"):
        q = params["q"]
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(sea_shipment__container_number__icontains=q))
    return qs


class ActionDashboardView(PermissionRequiredMixin, generic.TemplateView):
    permission_required = "actions.view_action"
    template_name = "actions/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        base = filter_actions(self.request, Action.objects.select_related("owner", "customer", "sea_shipment").annotate(
            cost_total=Sum("costs__amount")))
        open_qs = base.filter(status__in=Action.OPEN_STATUSES)
        columns = [
            {"key": key, "label": label, "items": list(open_qs.filter(status=key, kind=Action.KIND_ACTION))}
            for key, label in Action.STATUS_CHOICES if key in Action.OPEN_STATUSES
        ]
        escalation_levels = [
            {"level": level, "label": label, "items": list(open_qs.filter(kind=Action.KIND_ESCALATION, escalation_level=level))}
            for level, label in Action.LEVEL_CHOICES
        ]
        context.update({
            "columns": columns,
            "escalation_levels": escalation_levels,
            "overdue": open_qs.filter(due_date__lt=today),
            "due_today": open_qs.filter(due_date=today),
            "recently_done": base.filter(status="gereed", completed_at__isnull=False).order_by("-completed_at")[:10],
            "by_owner": open_qs.values("owner__name").annotate(n=Count("id")).order_by("-n"),
            "employees": Employee.objects.filter(active=True),
            "customers": Customer.objects.filter(active=True),
            "params": self.request.GET,
            "cost_totals": cost_summary(ExtraCost.objects.filter(action__in=open_qs)),
        })
        return context


class ActionListView(CrudListView):
    model = Action
    namespace = "actions"
    template_name = "actions/action_list.html"
    list_display = ["title", "kind", "status", "priority", "owner", "customer", "due_date"]
    search_fields = ["title", "description", "sea_shipment__container_number", "customer__name"]
    list_filters = ["kind", "status", "owner", "customer"]
    detail_url_name = "actions:action_detail"


class ActionDetailView(PermissionRequiredMixin, generic.DetailView):
    permission_required = "actions.view_action"
    model = Action
    template_name = "actions/action_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        costs = self.object.costs.all()
        context.update({"costs": costs, "cost_form": InlineCostForm(), "cost_totals": cost_summary(costs),
                        "total": costs.aggregate(t=Sum("amount"))["t"] or Decimal("0")})
        return context


class ActionCreateView(CrudCreateView):
    model = Action
    namespace = "actions"
    detail_url_name = "actions:action_detail"

    def get_form_class(self):
        from .forms import ActionForm

        return ActionForm


class ActionUpdateView(CrudUpdateView):
    model = Action
    namespace = "actions"
    detail_url_name = "actions:action_detail"

    def get_form_class(self):
        from .forms import ActionForm

        return ActionForm


@require_POST
@permission_required("actions.add_extracost", raise_exception=True)
def add_cost(request, pk):
    action = get_object_or_404(Action, pk=pk)
    form = InlineCostForm(request.POST)
    if form.is_valid():
        cost = form.save(commit=False)
        cost.action = action
        cost.created_by = request.user
        cost.save()
        messages.success(request, "Kosten toegevoegd.")
    else:
        messages.error(request, "Kosten niet opgeslagen: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in form.errors.items()))
    return redirect("actions:action_detail", pk=pk)


@require_POST
@permission_required("actions.change_action", raise_exception=True)
def set_status(request, pk):
    action = get_object_or_404(Action, pk=pk)
    status = request.POST.get("status")
    if status in dict(Action.STATUS_CHOICES):
        action.status = status
        action.save()
    if request.POST.get("escalate"):
        action.kind = Action.KIND_ESCALATION
        action.escalation_level = min((action.escalation_level or 0) + 1, 4)
        action.save()
        messages.warning(request, f"Geëscaleerd naar niveau {action.escalation_level}.")
    return redirect(request.POST.get("next") or "actions:dashboard")


class CostListView(CrudListView):
    model = ExtraCost
    namespace = "actions"
    template_name = "actions/cost_list.html"
    list_display = ["cost_date", "description", "cost_type", "customer", "sea_shipment", "amount", "responsibility", "status"]
    search_fields = ["description", "customer__name", "sea_shipment__container_number", "invoice_reference"]
    list_filters = ["responsibility", "status", "cost_type", "customer"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("customer", "sea_shipment", "action")
        if self.request.GET.get("van"):
            qs = qs.filter(cost_date__gte=self.request.GET["van"])
        if self.request.GET.get("tot"):
            qs = qs.filter(cost_date__lte=self.request.GET["tot"])
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.object_list
        context["cost_totals"] = cost_summary(qs)
        context["grand_total"] = qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")
        context["by_customer"] = qs.values("customer__name").annotate(total=Sum("amount"), n=Count("id")).order_by("-total")[:15]
        return context

    def render_to_response(self, context, **kwargs):
        if self.request.GET.get("export") == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="extra-kosten.csv"'
            response.write("﻿")
            writer = csv.writer(response, delimiter=";")
            writer.writerow(["Datum", "Omschrijving", "Soort", "Klant", "Container", "Bedrag", "Valuta", "Verantwoordelijk", "Status", "Referentie"])
            for c in self.object_list:
                writer.writerow([c.cost_date.strftime("%d-%m-%Y"), c.description, c.get_cost_type_display(), c.customer or "",
                                 c.sea_shipment.container_number if c.sea_shipment else "", str(c.amount).replace(".", ","),
                                 c.currency, c.get_responsibility_display(), c.get_status_display(), c.invoice_reference])
            return response
        return super().render_to_response(context, **kwargs)
