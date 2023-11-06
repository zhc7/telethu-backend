from django.urls import path, re_path

from . import views

urlpatterns = [
    re_path(r"(?P<hash_code>[a-f0-9]+)/", views.load),
]
