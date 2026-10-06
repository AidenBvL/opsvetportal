from django.urls import path

from core.crud import CrudDeleteView

from . import views
from .models import Document

app_name = "documents"


class DocumentDeleteView(CrudDeleteView):
    model = Document
    namespace = "documents"


urlpatterns = [
    path("", views.DocumentListView.as_view(), name="list"),
    path("", views.DocumentListView.as_view(), name="document_list"),
    path("uploaden/", views.UploadView.as_view(), name="document_create"),
    path("<int:pk>/", views.DocumentDetailView.as_view(), name="document_detail"),
    path("<int:pk>/verwerken/", views.ReviewView.as_view(), name="review"),
    path("<int:pk>/opnieuw/", views.reprocess, name="reprocess"),
    path("<int:pk>/bewerken/", views.ReviewView.as_view(), name="document_update"),
    path("<int:pk>/verwijderen/", DocumentDeleteView.as_view(), name="document_delete"),
]
