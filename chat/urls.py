# chat/urls.py
from django.urls import path, re_path

from . import views


urlpatterns = [
    path("", views.index, name="index"),
    path("<str:room_name>/", views.room, name="room"),
    re_path(r'^chat/history/$', views.chat_history, name='chat_history_regex'),
]