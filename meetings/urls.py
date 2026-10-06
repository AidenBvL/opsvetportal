from django.urls import path

from . import views

app_name = "meetings"

urlpatterns = [
    path("", views.DayView.as_view(), name="day"),
    path("open/", views.OpenItemsView.as_view(), name="open_items"),
    path("punt/nieuw/", views.add_item, name="add_item"),
    path("blok/opslaan/", views.save_block, name="save_block"),
    path("punt/<int:pk>/", views.ItemUpdateView.as_view(), name="item_update"),
    path("punt/<int:pk>/actie/", views.item_action, name="item_action"),
]
