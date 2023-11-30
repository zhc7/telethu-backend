# chat/urls.py
from django.urls import path, re_path

from . import views


urlpatterns = [
    path("", views.index, name="index"),
    path("<str:room_name>/", views.room, name="room"),
    re_path("history", views.chat_history),
    path("filter", views.filter_history)
]
