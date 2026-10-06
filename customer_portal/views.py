from datetime import timedelta

from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from shipments.models import RoadTransport, SeaShipment


def _customer(request):
    customer = getattr(request, "portal_customer", None)
    if customer is None:
        raise Http404("Alleen voor klantaccounts.")
    return customer


def home(request):
    customer = _customer(request)
    q = request.GET.get("q", "").strip()
    since = timezone.now() - timedelta(days=30)
    sea = SeaShipment.objects.filter(customer=customer).select_related("shipping_line", "inspection_point")
    road = RoadTransport.objects.filter(customer=customer).select_related("carrier", "sea_shipment")
    if q:
        sea = sea.filter(Q(container_number__icontains=q.replace(" ", "")) | Q(customer_reference__icontains=q)
                         | Q(bl_number__icontains=q) | Q(cory_reference__icontains=q))
        road = road.filter(Q(customer_reference__icontains=q) | Q(cory_reference__icontains=q))
    return render(request, "customer_portal/home.html", {
        "customer": customer, "q": q,
        "sea_open": sea.filter(status__in=SeaShipment.OPEN_STATUSES).order_by("eta"),
        "sea_recent": sea.exclude(status__in=SeaShipment.OPEN_STATUSES).filter(updated_at__gte=since).order_by("-updated_at")[:30],
        "road_open": road.filter(status__in=RoadTransport.OPEN_STATUSES).order_by("loading_at"),
    })


def container(request, pk):
    customer = _customer(request)
    shipment = get_object_or_404(SeaShipment.objects.select_related("shipping_line", "inspection_point"), pk=pk, customer=customer)
    updates = shipment.tracking_updates.filter(success=True).exclude(eta__isnull=True)[:20]
    return render(request, "customer_portal/container.html", {
        "customer": customer, "s": shipment, "updates": updates,
        "road": shipment.road_transports.select_related("carrier"),
    })
