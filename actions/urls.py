from django.urls import path

from core.crud import CrudDeleteView, crud_urls

from . import views
from .forms import ExtraCostForm
from .models import Action, ExtraCost

app_name = "actions"


class ActionDeleteView(CrudDeleteView):
    model = Action
    namespace = "actions"


urlpatterns = [
    path("", views.ActionDashboardView.as_view(), name="dashboard"),
    path("lijst/", views.ActionListView.as_view(), name="action_list"),
    path("nieuw/", views.ActionCreateView.as_view(), name="action_create"),
    path("<int:pk>/", views.ActionDetailView.as_view(), name="action_detail"),
    path("<int:pk>/bewerken/", views.ActionUpdateView.as_view(), name="action_update"),
    path("<int:pk>/verwijderen/", ActionDeleteView.as_view(), name="action_delete"),
    path("<int:pk>/kosten/", views.add_cost, name="add_cost"),
    path("<int:pk>/status/", views.set_status, name="set_status"),
    *crud_urls(
        ExtraCost, "actions", slug="kosten", form_class=ExtraCostForm, list_view=views.CostListView,
    ),
]
