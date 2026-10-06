from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import generic
from django.views.decorators.http import require_POST

from core.crud import CrudListView
from shipments.models import SeaShipment

from .forms import DocumentReviewForm, UploadForm
from .models import Document
from .parser import process_document


class DocumentListView(CrudListView):
    model = Document
    namespace = "documents"
    template_name = "documents/list.html"
    list_display = ["original_name", "doc_type", "customer", "status", "extraction_method", "created_at"]
    search_fields = ["original_name", "extracted_text", "customer__name"]
    list_filters = ["doc_type", "status", "customer"]


class UploadView(PermissionRequiredMixin, generic.CreateView):
    permission_required = "documents.add_document"
    form_class = UploadForm
    template_name = "documents/upload.html"

    def form_valid(self, form):
        document = form.save(commit=False)
        document.original_name = form.cleaned_data["file"].name
        document.uploaded_by = self.request.user
        document.save()
        process_document(document)
        if document.status == "fout":
            messages.error(self.request, f"Tekstherkenning mislukt: {document.error}")
        else:
            found = len(document.extracted_data.get("containers", []))
            messages.success(self.request, f"Document verwerkt ({document.extraction_method}); {found} container(s) herkend.")
        return redirect("documents:review", pk=document.pk)


class ReviewView(PermissionRequiredMixin, generic.FormView):
    permission_required = "documents.change_document"
    form_class = DocumentReviewForm
    template_name = "documents/review.html"

    def dispatch(self, request, *args, **kwargs):
        self.document = get_object_or_404(Document, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        d = self.document.extracted_data or {}
        eta = None
        if d.get("eta"):
            eta = timezone.make_aware(datetime.combine(datetime.fromisoformat(d["eta"]).date(), time(8)))
        return {
            "customer": self.document.customer_id,
            "shipping_line": d.get("shipping_line_id"),
            "inspection_point": d.get("inspection_point_id"),
            "customer_reference": d.get("customer_reference", ""),
            "bl_number": d.get("bl_number", ""),
            "booking_number": d.get("booking_number", ""),
            "vessel_name": d.get("vessel_name", ""),
            "voyage": d.get("voyage", ""),
            "eta": eta,
            "port_of_loading": d.get("port_of_loading", ""),
            "port_of_discharge": d.get("port_of_discharge", "") or "NLRTM",
            "ched_number": d.get("ched_number", ""),
            "goods_description": d.get("goods_description", ""),
            "temperature_setpoint": d.get("temperature_setpoint") or None,
            "inspection_required": True,
            "container_numbers": "\n".join(c["container_number"] for c in d.get("containers", [])),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        numbers = [c["container_number"] for c in (self.document.extracted_data or {}).get("containers", [])]
        context.update({
            "document": self.document,
            "existing": SeaShipment.objects.filter(container_number__in=numbers, status__in=SeaShipment.OPEN_STATUSES).select_related("customer"),
            "containers": (self.document.extracted_data or {}).get("containers", []),
        })
        return context

    @transaction.atomic
    def form_valid(self, form):
        data = form.cleaned_data
        details = {c["container_number"]: c for c in (self.document.extracted_data or {}).get("containers", [])}
        fields = ["customer_reference", "cory_reference", "bl_number", "booking_number", "vessel_name", "voyage", "eta",
                  "port_of_loading", "port_of_discharge", "ched_number", "goods_description", "temperature_setpoint"]
        created, updated = 0, 0
        for number in data["container_numbers"]:
            shipment = SeaShipment.objects.filter(container_number=number, status__in=SeaShipment.OPEN_STATUSES).first()
            if shipment:
                for name in fields:
                    if data.get(name) not in (None, "") and not getattr(shipment, name):
                        setattr(shipment, name, data[name])
                for name in ("shipping_line", "inspection_point"):
                    if data.get(name) and not getattr(shipment, f"{name}_id"):
                        setattr(shipment, name, data[name])
                shipment.save()
                updated += 1
            else:
                extra = details.get(number, {})
                shipment = SeaShipment.objects.create(
                    customer=data["customer"], shipping_line=data["shipping_line"], inspection_point=data["inspection_point"],
                    inspection_required=data["inspection_required"], container_number=number,
                    container_type=extra.get("container_type") or "40RH", seal_number=extra.get("seal_number", ""),
                    created_by=self.request.user, **_shipment_values(data, fields),
                )
                created += 1
            self.document.sea_shipments.add(shipment)
        self.document.customer = data["customer"]
        self.document.status = "gekoppeld"
        self.document.save()
        messages.success(self.request, f"{created} dossier(s) aangemaakt, {updated} bestaande bijgewerkt.")
        return redirect("shipments:sea_list")


class DocumentDetailView(PermissionRequiredMixin, generic.DetailView):
    permission_required = "documents.view_document"
    model = Document
    template_name = "documents/detail.html"


@require_POST
@permission_required("documents.change_document", raise_exception=True)
def reprocess(request, pk):
    document = get_object_or_404(Document, pk=pk)
    process_document(document)
    messages.info(request, "Document opnieuw verwerkt.")
    return redirect("documents:review", pk=pk)


def _shipment_values(data, fields):
    nullable = {"eta", "temperature_setpoint"}
    return {name: data.get(name) if name in nullable else (data.get(name) or "") for name in fields}
