from django.urls import path

from .crud import crud_urls
from .models import Customer, InspectionPoint, RoadCarrier, ShippingLine
from . import views

app_name = "core"

urlpatterns = [
    path("klanten/<int:pk>/", views.CustomerDetailView.as_view(), name="customer_detail"),
    path("klanten/<int:pk>/klantaccount/", views.customer_account_create, name="customer_account_create"),
    path("klanten/<int:pk>/klantaccount/<int:user_id>/", views.customer_account_action, name="customer_account_action"),
    *crud_urls(
        Customer, "core", slug="klanten",
        fields=["name", "code", "nationality", "vat_number", "eori_number", "street", "postal_code", "city", "country",
                "contact_name", "email", "phone", "account_manager", "notes", "active"],
        list_display=["name", "code", "nationality", ("address", "adres"), "contact_name", "email", "active"],
        search_fields=["name", "code", "city", "contact_name", "email"],
        list_filters=["active"],
        detail_url_name="core:customer_detail",
    ),
    *crud_urls(
        ShippingLine, "core", slug="rederijen",
        fields=["name", "scac", "website", "tracking_url_template", "contact_email", "contact_phone", "tracking_provider", "api_base_url",
                "api_key_env", "api_key_header", "oauth_token_url", "oauth_client_id_env", "oauth_client_secret_env",
                "notes", "active"],
        list_display=["name", "scac", "tracking_provider", "contact_email", "contact_phone", "active"],
        search_fields=["name", "scac"],
    ),
    *crud_urls(
        RoadCarrier, "core", slug="vervoerders",
        fields=["name", "contact_name", "email", "phone", "city", "country", "reefer_capable", "adr_capable", "notes", "active"],
        list_display=["name", "contact_name", "email", "phone", "city", "reefer_capable", "active"],
        search_fields=["name", "contact_name", "city"],
    ),
    *crud_urls(
        InspectionPoint, "core", slug="keurpunten",
        fields=["name", "point_type", "traces_code", "street", "city", "email", "phone", "opening_hours",
                "handles_veterinary", "handles_phytosanitary", "notes", "active"],
        list_display=["name", "point_type", "traces_code", "city", "phone", "opening_hours", "handles_veterinary", "active"],
        search_fields=["name", "traces_code", "city"],
        list_filters=["point_type"],
    ),
    path("accounts/", views.UserListView.as_view(), name="user_list"),
    path("accounts/nieuw/", views.UserCreateView.as_view(), name="user_create"),
    path("accounts/<int:pk>/", views.UserUpdateView.as_view(), name="user_update"),
    path("rollen/nieuw/", views.GroupCreateView.as_view(), name="group_create"),
    path("rollen/<int:pk>/", views.GroupUpdateView.as_view(), name="group_update"),
    path("wijzigingslog/", views.AuditLogView.as_view(), name="auditlog"),
    path("mijn-meldingen/", views.NotificationPreferenceView.as_view(), name="notification_prefs"),
]
