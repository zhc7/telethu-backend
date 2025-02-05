from django.urls import path, re_path

from . import views

urlpatterns = [
    path("login", views.login, name="login"),
    path("login_with_email", views.login_with_email, name="login_with_email"),
    path("receive_code", views.receive_code, name="receive_code"),
    path("register", views.register, name="register"),
    path("logout", views.logout, name="logout"),
    path("<int:user_id>", views.get_user_info, name="get_user_info"),
    path("friends/list", views.get_friend_list, name="get_friend_list"),
    path("friends/apply_list", views.get_apply_list, name="get_apply_list"),
    path("friends/you_apply_list", views.get_you_apply_list, name="get_you_apply_list"),
    path("verify/<str:signed_data>/", views.verification, name="verify"),
    path("verify/sendemail", views.sendemail, name="sendemail"),
    re_path(r"avatar/(?P<hash_code>[a-f0-9]+)?", views.avatar, name="avatar"),
    path("profile", views.profile, name="profile"),
    path("user_search", views.user_search, name="user_search"),
    path("delete_user", views.delete_user, name="delete_user"),
    path("block_user_list", views.block_user_list, name="block_user_list"),
    path("edit_profile", views.edit_profile, name="edit_profile"),
    path("email_exists/<str:query_email>", views.email_exists, name="email_exists"),
    path("group_candidates/<int:group_id>", views.group_candidates, name="group_candidates"),
]
