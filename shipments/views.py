from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import generic
from django.views.decorators.http import require_POST

from core.audit import history_for
from core.crud import CrudCreateView, CrudListView, CrudUpdateView
from documents.models import Document

from .forms import BulkContainerForm, RoadTransportForm, SeaShipmentForm
from .models import INSPECTION_STATUS_CHOICES, RoadTransport, SeaShipment
from .tracking.service import refresh_all, refresh_shipment


SEA_VIEWS = [
    ("open", "Open"),
    ("week", "Aankomst ≤ 7 dagen"),
    ("keuring", "Keuring lopend"),
    ("ched", "CHED aanmelden"),
    ("gewisseld", "Schipwissels"),
    ("demurrage", "Vrije dagen bijna op"),
    ("alle", "Alle"),
]


def sea_view_filter(qs, view):
    from datetime import timedelta

    today = timezone.localdate()
    open_qs = qs.filter(status__in=SeaShipment.OPEN_STATUSES)
    return {
        "open": open_qs,
        "week": open_qs.filter(eta__date__lte=today + timedelta(days=7), ata__isnull=True),
        "keuring": open_qs.filter(inspection_required=True).exclude(inspection_status__in=["vrijgegeven", "n.v.t."]),
        "ched": open_qs.filter(inspection_required=True, inspection_status="aan_te_melden"),
        "gewisseld": open_qs.filter(vessel_changed=True),
        "demurrage": open_qs.filter(free_time_until__isnull=False, free_time_until__lte=today + timedelta(days=2)),
        "alle": qs,
    }.get(view, open_qs)


class SeaListView(CrudListView):
    model = SeaShipment
    namespace = "shipments"
    template_name = "shipments/sea_list.html"
    search_fields = ["container_number", "customer_reference", "cory_reference", "bl_number", "booking_number",
                     "vessel_name", "customer__name", "ched_number"]
    list_filters = ["customer", "shipping_line", "inspection_point", "handler"]
    paginate_by = 100

    def get_queryset(self):
        qs = super().get_queryset().select_related("customer", "shipping_line", "inspection_point", "handler")
        return sea_view_filter(qs, self.request.GET.get("weergave", "open")).order_by("eta")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base = SeaShipment.objects.all()
        context["view"] = self.request.GET.get("weergave", "open")
        context["views"] = [{"key": k, "label": label, "count": sea_view_filter(base, k).count()} for k, label in SEA_VIEWS]
        context["now"] = timezone.now()
        return context

    def render_to_response(self, context, **kwargs):
        if self.request.GET.get("export") == "csv":
            import csv

            from django.http import HttpResponse

            from core.ports import port_label

            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="zeevracht.csv"'
            response.write("\ufeff")
            writer = csv.writer(response, delimiter=";")
            writer.writerow(["Container", "Klant", "Klantref", "Cory ref", "B/L", "Rederij", "Schip", "Reis", "Laadhaven", "Loshaven", "Terminal", "ETA", "ATA",
                             "Keurpunt", "CHED", "Keuring", "Status", "Vrije dagen t/m", "Behandelaar"])
            fmt = lambda d: timezone.localtime(d).strftime("%d-%m-%Y %H:%M") if d else ""  # noqa: E731
            for s in self.object_list:
                writer.writerow([s.container_number, s.customer, s.customer_reference, s.cory_reference, s.bl_number,
                                 s.shipping_line or "", s.vessel_name, s.voyage, port_label(s.port_of_loading),
                                 port_label(s.port_of_discharge), s.terminal, fmt(s.eta), fmt(s.ata), s.inspection_point or "",
                                 s.ched_number, s.get_inspection_status_display(), s.get_status_display(),
                                 s.free_time_until.strftime("%d-%m-%Y") if s.free_time_until else "", s.handler or ""])
            return response
        return super().render_to_response(context, **kwargs)


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
            "documents": s.documents.select_related("uploaded_by").defer("content", "extracted_text"),
            "doc_types": Document.TYPE_CHOICES,
            "meeting_items": s.meeting_items.select_related("meeting")[:10],
            "history": history_for(s),
            "work_count": s.actions.count() + s.extra_costs.count(),
            "inspection_choices": INSPECTION_STATUS_CHOICES,
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
        t = self.object
        documents = t.documents.select_related("uploaded_by").defer("content", "extracted_text")
        stops = [
            {"title": "Laden", "icon": "bi-box-arrow-up", "address": t.loading_address, "place": t.loading_place,
             "reference": t.loading_reference, "when_label": "Gepland", "when": t.loading_at},
            {"title": "Lossen", "icon": "bi-box-arrow-in-down", "address": t.unloading_address, "place": t.unloading_place,
             "reference": t.unloading_reference, "when_label": "Levering gepland", "when": t.delivery_planned_at,
             "until": t.delivery_window_until, "done": t.delivered_at},
        ]
        return super().get_context_data(history=history_for(t), documents=documents, doc_types=Document.TYPE_CHOICES,
                                        stops=stops, **kwargs)


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
                from core.ports import port_label

                initial.update({
                    "customer": sea.customer_id, "customer_reference": sea.customer_reference,
                    "cory_reference": sea.cory_reference, "inspection_required": sea.inspection_required,
                    "inspection_point": sea.inspection_point_id, "ched_number": sea.ched_number,
                    "goods_description": sea.goods_description, "temperature_setpoint": sea.temperature_setpoint,
                    "gross_weight_kg": sea.gross_weight_kg, "direction": "import", "transport_type": "container",
                    # De container staat op de terminal van de loshaven.
                    "loading_place": f"{sea.terminal}, {port_label(sea.port_of_discharge)}" if sea.terminal else port_label(sea.port_of_discharge),
                })
        customer_id = initial.get("customer")
        if customer_id and "unloading_address" not in initial:
            from core.models import Address

            default = Address.objects.filter(customer_id=customer_id, is_default=True, active=True).first()
            if default:
                initial.update({"unloading_address": default.pk, "unloading_place": default.one_line,
                                "driver_instructions": default.instructions})
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


@require_POST
@permission_required("shipments.change_seashipment", raise_exception=True)
def quick_update(request, pk):
    """Snel één veld wijzigen vanuit het dossier (status, keuringsstatus, behandelaar)."""
    shipment = get_object_or_404(SeaShipment, pk=pk)
    changed = []
    if request.POST.get("status") in dict(SeaShipment.STATUS_CHOICES):
        shipment.status = request.POST["status"]
        changed.append("status")
    from .models import INSPECTION_STATUS_CHOICES

    if request.POST.get("inspection_status") in dict(INSPECTION_STATUS_CHOICES):
        shipment.inspection_status = request.POST["inspection_status"]
        changed.append("keuringsstatus")
    if "customs_cleared" in request.POST:
        shipment.customs_cleared = request.POST["customs_cleared"] == "1"
        changed.append("douane")
    if changed:
        shipment.save()
        messages.success(request, f"{shipment.container_number}: {', '.join(changed)} bijgewerkt.")
    if request.POST.get("next", "").startswith("/"):
        return redirect(request.POST["next"])
    return redirect("shipments:sea_detail", pk=pk)


@require_POST
@permission_required("shipments.change_seashipment", raise_exception=True)
def paste_tracking(request, pk):
    """Verwerk tekst die van de trackingpagina van de rederij is gekopieerd."""
    from .paste import parse_tracking_text
    from .tracking.service import apply_result

    shipment = get_object_or_404(SeaShipment, pk=pk)
    result = parse_tracking_text(request.POST.get("text", ""))
    if result is None:
        messages.error(request, "Geen schip of ETA gevonden in de geplakte tekst. Kopieer de hele trackingpagina (Ctrl+A, Ctrl+C).")
        return redirect("shipments:sea_detail", pk=pk)
    update = apply_result(shipment, result, provider_name="geplakt")
    parts = [p for p in [result.vessel_name, result.voyage,
                         f"ETA {timezone.localtime(result.eta):%d-%m %H:%M}" if result.eta else ""] if p]
    messages.success(request, "Overgenomen: " + " · ".join(parts) + (f". {update.message}" if update.message else ""))
    return redirect("shipments:sea_detail", pk=pk)
