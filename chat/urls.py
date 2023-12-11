# chat/urls.py
from django.urls import path, re_path

from . import views


urlpatterns = [
    re_path("history", views.chat_history, name="chat_history"),
    path("filter", views.filter_history, name="filter_history"),
    path("message/<int:message_id>", views.get_message, name="message"),
]
