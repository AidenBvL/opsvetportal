from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import generic

from core.audit import history_for
from django.views.decorators.http import require_POST

from core.crud import CrudCreateView, CrudListView, CrudUpdateView

from .forms import BulkContainerForm, RoadTransportForm, SeaShipmentForm
from .models import RoadTransport, SeaShipment
from .tracking.service import refresh_all, refresh_shipment


class SeaListView(CrudListView):
    model = SeaShipment
    namespace = "shipments"
    template_name = "shipments/sea_list.html"
    search_fields = ["container_number", "customer_reference", "cory_reference", "bl_number", "vessel_name", "customer__name", "ched_number"]
    list_filters = ["status", "customer", "shipping_line", "inspection_point", "inspection_status"]
    paginate_by = 100

    def get_queryset(self):
        qs = super().get_queryset().select_related("customer", "shipping_line", "inspection_point", "handler")
        view = self.request.GET.get("weergave", "open")
        if view == "open":
            qs = qs.filter(status__in=SeaShipment.OPEN_STATUSES)
        elif view == "gewisseld":
            qs = qs.filter(vessel_changed=True, status__in=SeaShipment.OPEN_STATUSES)
        elif view == "keuring":
            qs = qs.filter(inspection_required=True, status__in=SeaShipment.OPEN_STATUSES).exclude(inspection_status="vrijgegeven")
        return qs.order_by("eta")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["view"] = self.request.GET.get("weergave", "open")
        context["now"] = timezone.now()
        return context


class SeaDetailView(PermissionRequiredMixin, generic.DetailView):
    permission_required = "shipments.view_seashipment"
    model = SeaShipment
    template_name = "shipments/sea_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        s = self.object
        context.update({
            "updates": s.tracking_updates.all()[:30],
            "vessel_history": s.tracking_updates.filter(vessel_changed=True),
            "actions": s.actions.all(),
            "costs": s.extra_costs.all(),
            "road": s.road_transports.select_related("carrier"),
            "documents": s.documents.all(),
            "meeting_items": s.meeting_items.select_related("meeting")[:10],
            "history": history_for(s),
        })
        return context


class SeaCreateView(CrudCreateView):
    model = SeaShipment
    namespace = "shipments"
    form_class = SeaShipmentForm
    detail_url_name = "shipments:sea_detail"


class SeaUpdateView(CrudUpdateView):
    model = SeaShipment
    namespace = "shipments"
    form_class = SeaShipmentForm
    detail_url_name = "shipments:sea_detail"


class BulkCreateView(PermissionRequiredMixin, generic.FormView):
    permission_required = "shipments.add_seashipment"
    form_class = BulkContainerForm
    template_name = "shipments/bulk_form.html"

    def get_initial(self):
        return {**super().get_initial(), **self.request.GET.dict()}

    def form_valid(self, form):
        data = form.cleaned_data
        created = []
        for number in data["container_numbers"]:
            created.append(SeaShipment.objects.create(
                customer=data["customer"], shipping_line=data["shipping_line"], inspection_point=data["inspection_point"],
                customer_reference=data["customer_reference"], cory_reference=data["cory_reference"],
                bl_number=data["bl_number"], vessel_name=data["vessel_name"], voyage=data["voyage"], eta=data["eta"],
                inspection_required=data["inspection_required"], container_number=number, created_by=self.request.user,
            ))
        messages.success(self.request, f"{len(created)} container(s) aangemaakt.")
        return redirect("shipments:sea_list")


@require_POST
@permission_required("shipments.refresh_tracking", raise_exception=True)
def refresh_view(request, pk):
    shipment = get_object_or_404(SeaShipment, pk=pk)
    update = refresh_shipment(shipment)
    if update is None:
        messages.info(request, "Automatische tracking staat uit voor deze rederij.")
    elif update.success:
        messages.success(request, update.message or "Tracking bijgewerkt, geen wijzigingen.")
    else:
        messages.error(request, f"Tracking mislukt: {update.message}")
    return redirect("shipments:sea_detail", pk=pk)


@require_POST
@permission_required("shipments.refresh_tracking", raise_exception=True)
def refresh_all_view(request):
    updates = refresh_all()
    changed = [u for u in updates if u.eta_changed or u.vessel_changed]
    failed = [u for u in updates if not u.success]
    messages.success(request, f"{len(updates)} containers gecontroleerd, {len(changed)} met wijzigingen, {len(failed)} mislukt.")
    return redirect("shipments:sea_list")


@require_POST
@permission_required("shipments.change_seashipment", raise_exception=True)
def ack_vessel_change(request, pk):
    shipment = get_object_or_404(SeaShipment, pk=pk)
    shipment.vessel_changed = False
    shipment.save(update_fields=["vessel_changed", "updated_at"])
    messages.info(request, "Schipwissel gemarkeerd als gezien.")
    return redirect("shipments:sea_detail", pk=pk)


class RoadListView(CrudListView):
    model = RoadTransport
    namespace = "shipments"
    template_name = "shipments/road_list.html"
    search_fields = ["customer_reference", "cory_reference", "truck_plate", "trailer_plate", "cmr_number", "customer__name",
                     "sea_shipment__container_number"]
    list_filters = ["status", "customer", "carrier", "direction", "inspection_status"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("customer", "carrier", "sea_shipment", "inspection_point")
        if self.request.GET.get("weergave", "open") == "open":
            qs = qs.filter(status__in=RoadTransport.OPEN_STATUSES)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["view"] = self.request.GET.get("weergave", "open")
        return context


class RoadDetailView(PermissionRequiredMixin, generic.DetailView):
    permission_required = "shipments.view_roadtransport"
    model = RoadTransport
    template_name = "shipments/road_detail.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(history=history_for(self.object), **kwargs)


class RoadCreateView(CrudCreateView):
    model = RoadTransport
    namespace = "shipments"
    form_class = RoadTransportForm
    detail_url_name = "shipments:road_detail"

    def get_initial(self):
        initial = super().get_initial()
        sea_id = self.request.GET.get("sea_shipment")
        if sea_id:
            sea = SeaShipment.objects.filter(pk=sea_id).first()
            if sea:
                initial.update({
                    "customer": sea.customer_id, "customer_reference": sea.customer_reference,
                    "cory_reference": sea.cory_reference, "inspection_required": sea.inspection_required,
                    "inspection_point": sea.inspection_point_id, "ched_number": sea.ched_number,
                    "goods_description": sea.goods_description, "temperature_setpoint": sea.temperature_setpoint,
                })
        return initial


class RoadUpdateView(CrudUpdateView):
    model = RoadTransport
    namespace = "shipments"
    form_class = RoadTransportForm
    detail_url_name = "shipments:road_detail"


def search(request):
    """Globale zoekfunctie op container, referentie, B/L of klant."""
    from django.shortcuts import render

    from core.models import Customer

    q = request.GET.get("q", "").strip()
    results = {"sea": [], "road": [], "customers": []}
    if q:
        results["sea"] = SeaShipment.objects.filter(
            Q(container_number__icontains=q.replace(" ", "")) | Q(customer_reference__icontains=q) | Q(cory_reference__icontains=q)
            | Q(bl_number__icontains=q) | Q(ched_number__icontains=q) | Q(vessel_name__icontains=q)
        ).select_related("customer")[:30]
        results["road"] = RoadTransport.objects.filter(
            Q(customer_reference__icontains=q) | Q(cory_reference__icontains=q) | Q(cmr_number__icontains=q)
            | Q(truck_plate__icontains=q) | Q(trailer_plate__icontains=q)
        ).select_related("customer")[:30]
        results["customers"] = Customer.objects.filter(Q(name__icontains=q) | Q(code__icontains=q))[:10]
    if len(results["sea"]) == 1 and not results["road"] and not results["customers"]:
        return redirect("shipments:sea_detail", pk=results["sea"][0].pk)
    return render(request, "shipments/search.html", {"q": q, **results})
