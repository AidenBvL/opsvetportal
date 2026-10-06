from django.contrib import admin

from .models import Customer, InspectionPoint, Port, RoadCarrier, ShippingLine, Terminal

admin.site.register([Customer, InspectionPoint, Port, RoadCarrier, ShippingLine, Terminal])
