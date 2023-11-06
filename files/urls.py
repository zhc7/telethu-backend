from django.urls import path, re_path

from . import views

urlpatterns = [
    re_path(r"^upload/(?P<hash_code>[a-f0-9]+)/", views.upload),
    re_path(r"^download/(?P<hash_code>[a-f0-9]+)/", views.download),
]
