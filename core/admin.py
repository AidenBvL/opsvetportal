from django.contrib import admin

from .models import Address, Customer, InspectionPoint, Port, RoadCarrier, ShippingLine, Terminal

admin.site.register([Address, Customer, InspectionPoint, Port, RoadCarrier, ShippingLine, Terminal])
