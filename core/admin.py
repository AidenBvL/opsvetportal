from django.contrib import admin

from .models import Customer, InspectionPoint, Port, RoadCarrier, ShippingLine

admin.site.register([Customer, InspectionPoint, Port, RoadCarrier, ShippingLine])
