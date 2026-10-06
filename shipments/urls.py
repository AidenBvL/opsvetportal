from django.urls import path

from core.crud import CrudDeleteView

from . import views
from .models import RoadTransport, SeaShipment

app_name = "shipments"


class SeaDeleteView(CrudDeleteView):
    model = SeaShipment
    namespace = "shipments"


class RoadDeleteView(CrudDeleteView):
    model = RoadTransport
    namespace = "shipments"


urlpatterns = [
    path("zoeken/", views.search, name="search"),
    path("zeevracht/", views.SeaListView.as_view(), name="seashipment_list"),
    path("zeevracht/", views.SeaListView.as_view(), name="sea_list"),
    path("zeevracht/nieuw/", views.SeaCreateView.as_view(), name="seashipment_create"),
    path("zeevracht/meerdere/", views.BulkCreateView.as_view(), name="sea_bulk"),
    path("zeevracht/verversen/", views.refresh_all_view, name="sea_refresh_all"),
    path("zeevracht/<int:pk>/", views.SeaDetailView.as_view(), name="sea_detail"),
    path("zeevracht/<int:pk>/bewerken/", views.SeaUpdateView.as_view(), name="seashipment_update"),
    path("zeevracht/<int:pk>/verwijderen/", SeaDeleteView.as_view(), name="seashipment_delete"),
    path("zeevracht/<int:pk>/verversen/", views.refresh_view, name="sea_refresh"),
    path("zeevracht/<int:pk>/schipwissel-gezien/", views.ack_vessel_change, name="sea_ack_vessel"),
    path("zeevracht/<int:pk>/snel/", views.quick_update, name="sea_quick"),
    path("zeevracht/<int:pk>/plakken/", views.paste_tracking, name="sea_paste"),
    path("weg/", views.RoadListView.as_view(), name="roadtransport_list"),
    path("weg/", views.RoadListView.as_view(), name="road_list"),
    path("weg/nieuw/", views.RoadCreateView.as_view(), name="roadtransport_create"),
    path("weg/<int:pk>/", views.RoadDetailView.as_view(), name="road_detail"),
    path("weg/<int:pk>/bewerken/", views.RoadUpdateView.as_view(), name="roadtransport_update"),
    path("weg/<int:pk>/verwijderen/", RoadDeleteView.as_view(), name="roadtransport_delete"),
]
