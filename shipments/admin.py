from django.contrib import admin

from .models import RoadTransport, SeaShipment, TrackingUpdate


@admin.register(SeaShipment)
class SeaShipmentAdmin(admin.ModelAdmin):
    list_display = ["container_number", "customer", "shipping_line", "vessel_name", "eta", "status", "inspection_status"]
    list_filter = ["status", "shipping_line", "inspection_status"]
    search_fields = ["container_number", "customer_reference", "cory_reference", "bl_number"]


admin.site.register([RoadTransport, TrackingUpdate])
