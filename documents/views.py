import os
from datetime import datetime, time
from decimal import Decimal
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views import generic
from django.views.decorators.http import require_POST

from core.crud import CrudListView
from shipments.models import RoadTransport, SeaShipment

from .forms import DocumentReviewForm, ShipmentUploadForm, UploadForm
from .models import Document
from .parser import TEXT_EXTENSIONS, process_document

# Deze typen kan de browser zelf tonen; de rest wordt gedownload.
INLINE_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp", "image/bmp", "text/plain"}
SHIPMENT_KINDS = {"zee": (SeaShipment, "sea_shipments", "shipments:sea_detail"),
                  "weg": (RoadTransport, "road_transports", "shipments:road_detail")}


class DocumentListView(CrudListView):
    model = Document
    namespace = "documents"
    template_name = "documents/list.html"
    list_display = ["original_name", "doc_type", "customer", "status", "extraction_method", "created_at"]
    search_fields = ["original_name", "extracted_text", "customer__name"]
    list_filters = ["doc_type", "status", "customer"]

    def get_queryset(self):
        return super().get_queryset().defer("content")


class UploadView(PermissionRequiredMixin, generic.CreateView):
    permission_required = "documents.add_document"
    form_class = UploadForm
    template_name = "documents/upload.html"

    def form_valid(self, form):
        document = form.save(commit=False)
        document.original_name = form.cleaned_data["file"].name
        document.uploaded_by = self.request.user
        document.store_content()
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
        departed = d.get("departed_at") or None
        # Bij meerdere containers is het gewicht in de tekst meestal het totaal: dan per container uit het document.
        single = len(d.get("containers", [])) <= 1
        return {
            "customer": self.document.customer_id or d.get("customer_id"),
            "departed_at": departed and datetime.fromisoformat(departed).date(),
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
            "gross_weight_kg": (d.get("gross_weight_kg") or None) if single else None,
            "packages": (d.get("packages") or None) if single else None,
            "package_type": d.get("package_type", "") if single else "",
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
            "parties": [(label, (self.document.extracted_data or {}).get(key)) for key, label in
                        (("shipper", "Shipper"), ("consignee", "Consignee"), ("notify", "Notify party"))
                        if (self.document.extracted_data or {}).get(key)],
        })
        return context

    @transaction.atomic
    def form_valid(self, form):
        data = form.cleaned_data
        details = {c["container_number"]: c for c in (self.document.extracted_data or {}).get("containers", [])}
        if data.get("departed_at"):
            data["departed_at"] = timezone.make_aware(datetime.combine(data["departed_at"], time(12)))
        fields = ["customer_reference", "cory_reference", "bl_number", "booking_number", "vessel_name", "voyage", "eta",
                  "departed_at", "port_of_loading", "port_of_discharge", "ched_number", "goods_description", "temperature_setpoint",
                  *CARGO_FIELDS]
        created, updated, shipments = 0, 0, []
        multiple = len(data["container_numbers"]) > 1
        all_data = data
        for number in data["container_numbers"]:
            data = _with_container_cargo(all_data, details.get(number, {}), multiple)
            shipment = SeaShipment.objects.filter(container_number=number, status__in=SeaShipment.OPEN_STATUSES).first()
            if shipment:
                for name in fields:
                    if data.get(name) not in (None, "") and not getattr(shipment, name):
                        setattr(shipment, name, data[name])
                for name in ("shipping_line", "inspection_point"):
                    if data.get(name) and not getattr(shipment, f"{name}_id"):
                        setattr(shipment, name, data[name])
                if details.get(number, {}).get("seal_number") and not shipment.seal_number:
                    shipment.seal_number = details[number]["seal_number"]
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
            shipments.append(shipment)
        data = all_data
        self.document.customer = data["customer"]
        self.document.status = "gekoppeld"
        self.document.save()
        messages.success(self.request, f"{created} dossier(s) aangemaakt, {updated} bestaande bijgewerkt.")
        if len(shipments) == 1:
            return redirect(reverse("shipments:sea_detail", args=[shipments[0].pk]) + "#tab-docs")
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


@permission_required("documents.view_document", raise_exception=True)
def document_file(request, pk):
    """Het originele bestand, alleen voor ingelogde gebruikers met leesrecht. PDF's en foto's openen in de browser."""
    document = get_object_or_404(Document, pk=pk)
    try:
        data = document.read_bytes()
    except (FileNotFoundError, ValueError) as exc:
        raise Http404("Bestand niet meer aanwezig.") from exc
    content_type = document.content_type
    disposition = "inline" if content_type in INLINE_TYPES and not request.GET.get("download") else "attachment"
    name = str(document) or f"document-{document.pk}{document.extension}"
    response = HttpResponse(data, content_type=f"{content_type}; charset=utf-8" if content_type == "text/plain" else content_type)
    response["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{quote(name)}"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_POST
@permission_required("documents.add_document", raise_exception=True)
def upload_for_shipment(request, kind, pk):
    """Documenten direct bij een zeevracht-dossier of wegtransport uploaden en koppelen."""
    if kind not in SHIPMENT_KINDS:
        raise Http404
    model, relation, detail_url = SHIPMENT_KINDS[kind]
    shipment = get_object_or_404(model, pk=pk)
    back = reverse(detail_url, args=[shipment.pk]) + "#tab-docs"
    form = ShipmentUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect(back)
    for upload in form.cleaned_data["files"]:
        document = Document(file=upload, original_name=os.path.basename(upload.name), doc_type=form.cleaned_data["doc_type"],
                            customer=shipment.customer, uploaded_by=request.user, status="gekoppeld")
        document.store_content()
        document.save()
        getattr(document, relation).add(shipment)
        if document.extension in TEXT_EXTENSIONS:
            process_document(document)
            if document.status == "verwerkt":
                # Tekst is herkend, maar het document hoort al bij dit dossier.
                document.status = "gekoppeld"
                document.save(update_fields=["status", "updated_at"])
        if kind == "zee" and document.doc_type in {"bl", "arrival_notice"} and document.extracted_data.get("containers"):
            messages.info(request, format_html(
                '{} is uitgelezen. <a href="{}">Herkende gegevens controleren en overnemen</a>.',
                document, reverse("documents:review", args=[document.pk]),
            ))
    count = len(form.cleaned_data["files"])
    messages.success(request, f"{count} document(en) toegevoegd." if count != 1 else "Document toegevoegd.")
    return redirect(back)


@require_POST
@permission_required("documents.change_document", raise_exception=True)
def unlink_from_shipment(request, pk, kind, shipment_pk):
    if kind not in SHIPMENT_KINDS:
        raise Http404
    model, relation, detail_url = SHIPMENT_KINDS[kind]
    document = get_object_or_404(Document, pk=pk)
    getattr(document, relation).remove(shipment_pk)
    messages.info(request, f"{document} is losgekoppeld van dit dossier (het document zelf blijft bewaard).")
    return redirect(reverse(detail_url, args=[shipment_pk]) + "#tab-docs")


CARGO_FIELDS = ["gross_weight_kg", "packages", "package_type"]


def _with_container_cargo(data, detail, multiple):
    """Bij meerdere containers gaan gewicht en colli per container (uit het document) voor op het formulier."""
    if not multiple:
        return data
    data = dict(data)
    for name in CARGO_FIELDS:
        value = detail.get(name)
        if value:
            data[name] = Decimal(value) if name == "gross_weight_kg" else int(value) if name == "packages" else value
    return data


def _shipment_values(data, fields):
    nullable = {"eta", "departed_at", "temperature_setpoint", "gross_weight_kg", "packages"}
    return {name: data.get(name) if name in nullable else (data.get(name) or "") for name in fields}
