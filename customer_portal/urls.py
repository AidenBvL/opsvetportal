from django.urls import path

from . import views

app_name = "customer_portal"

urlpatterns = [
    path("", views.home, name="home"),
    path("container/<int:pk>/", views.container, name="container"),
]
