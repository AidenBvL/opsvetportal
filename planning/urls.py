from django.urls import path

from core.crud import crud_urls

from . import views
from .models import Absence, Department, Employee, Holiday

app_name = "planning"

urlpatterns = [
    path("", views.CalendarView.as_view(), name="calendar"),
    path("genereren/", views.generate_view, name="generate"),
    path("status/", views.set_status_view, name="set_status"),
    path("dienst/<str:day>/", views.ShiftEditView.as_view(), name="shift_edit"),
    path("thuiswerk/wissel/", views.toggle_wfh_view, name="toggle_wfh"),
    path("export.xlsx", views.export_excel, name="export"),
    path("medewerkers/<int:pk>/", views.EmployeeAgendaView.as_view(), name="employee_detail"),
    path("ics/<uuid:token>.ics", views.ics_feed, name="ics"),
    path("ruilen/", views.SwapListView.as_view(), name="swap_list"),
    path("ruilen/dienst/<int:pk>/", views.SwapCreateView.as_view(), name="swap_create"),
    path("ruilen/<int:pk>/", views.swap_action, name="swap_action"),
    *crud_urls(
        Employee, "planning", slug="medewerkers",
        fields=["name", "user", "job_title", "departments", "email", "phone", "wfh_days_per_week",
                "preferred_wfh_weekdays", "days_off", "in_shift_pool", "no_shift_weekdays", "active"],
        list_display=["name", "job_title", "departments", "wfh_days_per_week", "days_off", "in_shift_pool",
                      "no_shift_weekdays", "active"],
        search_fields=["name", "job_title"],
        list_filters=["in_shift_pool", "active"],
        detail_url_name="planning:employee_detail",
    ),
    *crud_urls(
        Absence, "planning", slug="afwezigheid",
        fields=["employee", "start_date", "end_date", "reason", "note"],
        list_display=["employee", "start_date", "end_date", "reason", "note"],
        search_fields=["employee__name", "note"],
        list_filters=["employee", "reason"],
    ),
    *crud_urls(
        Department, "planning", slug="afdelingen",
        fields=["name", "description"], list_display=["name", "description", "employees"],
    ),
    *crud_urls(
        Holiday, "planning", slug="feestdagen",
        fields=["date", "name"], list_display=["date", "name"],
    ),
]
