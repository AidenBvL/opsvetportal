from django.contrib import admin

from .models import Customer, InspectionPoint, RoadCarrier, ShippingLine

admin.site.register([Customer, InspectionPoint, RoadCarrier, ShippingLine])
