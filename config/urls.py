from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from core.views import DashboardView

admin.site.site_header = "OPS/VET Portaal - beheer"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/wachtwoord/", auth_views.PasswordChangeView.as_view(success_url="/"), name="password_change"),
    path("accounts/wachtwoord-vergeten/", auth_views.PasswordResetView.as_view(
        email_template_name="registration/password_reset_email.txt", subject_template_name="registration/password_reset_subject.txt",
        success_url="/accounts/wachtwoord-vergeten/verstuurd/"), name="password_reset"),
    path("accounts/wachtwoord-vergeten/verstuurd/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("accounts/reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(success_url="/accounts/reset/klaar/"), name="password_reset_confirm"),
    path("accounts/reset/klaar/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("klantportaal/", include("customer_portal.urls")),
    path("beheer/", include("core.urls")),
    path("agenda/", include("planning.urls")),
    path("overleg/", include("meetings.urls")),
    path("acties/", include("actions.urls")),
    path("zendingen/", include("shipments.urls")),
    path("documenten/", include("documents.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
