from django.urls import path

from . import views

urlpatterns = [
    path("login", views.login),
    path("register", views.register),
    path("logout", views.logout),
    path("friends/apply", views.apply_friend),
    path("friends/accept", views.accept_friend),
    path("friends/reject", views.reject_friend),
    path("friends/delete", views.delete_friend),
    path("friends/block", views.block_friend),
    path("friends/unblock", views.unblock_friend),
    path("friends/list", views.get_friend_list),
    path("friends/apply_list", views.get_apply_list),
    path("friends/you_apply_list", views.get_you_apply_list),
]
