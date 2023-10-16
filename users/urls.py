from django.urls import path, include
from . import views

urlpatterns = [
    path('login', views.login),
    path('register', views.register),
    path('logout', views.logout),
    path('friends/apply', views.apply_friend),
    path('friends/accept', views.accept_friend),
    path('friends/reject', views.reject_friend),
    path('friends/delete', views.delete_friend),
    path('friends/block', views.block_friend),
    path('friends/unblock', views.unblock_friend),
]
