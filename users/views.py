import hashlib
import json
import os

import magic
from django.core.signing import loads
from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from users.email import email_sender
from users.models import User, GroupList
from utils.data import UserData, GroupData
from utils.session import SessionData
from utils.uid import globalIdMaker
from utils.utils_jwt import hash_string_with_sha256, generate_jwt_token
from utils.utils_request import request_failed, request_success, BAD_METHOD
from utils.utils_require import check_require, require


def authentication(req: HttpRequest):
    # 检查请求方法
    if req.method != "POST":
        raise KeyError("Bad method", 400)
    body = json.loads(req.body)
    password = require(
        body, "password", "string", err_msg="Missing or error type of [password]"
    )
    user_email = require(
        body, "userEmail", "string", err_msg="Missing or error type of [email]"
    )
    if not User.objects.filter(userEmail=user_email, is_deleted=False).exists():
        raise KeyError("User not exists", 401)
    user = User.objects.get(userEmail=user_email, is_deleted=False)
    return user, password


@csrf_exempt  # 关闭csrf验证
def login(req: HttpRequest):
    try:
        user, password = authentication(req)
    except KeyError as e:
        error_message, status_code = str(e.args[0]), int(e.args[1])
        return request_failed(2, error_message, status_code=status_code)
    hashed_password = hash_string_with_sha256(password, num_iterations=5)
    if user.password != hashed_password:
        return request_failed(2, "Wrong password", status_code=401)
    user_id = user.id
    token = generate_jwt_token(user_id)
    session = SessionData(req)
    if session.user_id is not None:
        return request_failed(
            2,
            f"Login failed because user {session.user_id} has login",
            status_code=401,
        )
    session.user_id = user_id
    response_data = {
        "token": token,
        "user": UserData(
            id=user.id, name=user.username, avatar=user.avatar, email=user.userEmail
        ).model_dump(),
    }
    return request_success(response_data)


@csrf_exempt  # 关闭csrf验证
def logout(req: HttpRequest):
    try:
        user, password = authentication(req)
    except KeyError as e:
        error_message, status_code = str(e.args[0]), int(e.args[1])
        return request_failed(2, error_message, status_code=status_code)
    user_id = user.id
    session = SessionData(req)
    if user_id != session.user_id:
        return request_failed(2, "Logging out with the wrong user!", status_code=401)
    hashed_password = hash_string_with_sha256(password, num_iterations=5)
    if user.password != hashed_password:
        return request_failed(2, "Wrong password", status_code=401)
    session = SessionData(req)
    session.user_id = None
    return request_success()


@csrf_exempt  # 允许跨域,便于测试
def register(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD
    body = json.loads(req.body)
    username = require(
        body, "userName", "string", err_msg="Missing or error type of [userName]"
    )
    password = require(
        body, "password", "string", err_msg="Missing or error type of [password]"
    )
    user_email = require(
        body, "userEmail", "string", err_msg="Missing or error type of [email]"
    )
    if User.objects.filter(userEmail=user_email, is_deleted=False).exists():
        return request_failed(2, "userEmail already exists", status_code=401)
    if not check_require(username, "username"):
        return request_failed(2, "Invalid username", status_code=422)
    if not check_require(password, "password"):
        return request_failed(2, "Invalid password", status_code=422)
    if not check_require(user_email, "email"):
        return request_failed(2, "Invalid email", status_code=422)
    # 利用 SHA256 算法对新建用户的密码进行 5 次加密
    hashed_password = hash_string_with_sha256(password, num_iterations=5)
    user = User(
        id=globalIdMaker.get_id(),
        username=username,
        password=hashed_password,
        userEmail=user_email,
    )
    user.save()
    email_sender(req, user_email, user.id)
    return request_success()


@require_GET
def get_user_info(req: HttpRequest, user_id: int):
    if_user_exit = User.objects.filter(id=user_id, is_deleted=False).exists()
    if if_user_exit is False:
        if_group_exit = GroupList.objects.filter(group_id=user_id).exists()
        if if_group_exit is False:
            return request_failed(2, "No such user", status_code=404)
        else:
            group = GroupList.objects.get(group_id=user_id)
            response_data = GroupData(
                id=group.group_id,
                name=group.group_name,
                avatar=group.group_avatar,
                members=[member.id for member in group.group_members.all()],
                owner= None if group.group_owner is None else group.group_owner.id,
                admin=[admin.id for admin in group.group_admin.all()],
            ).model_dump()
    else:
        user = User.objects.get(id=user_id)
        response_data = UserData(
            id=user.id,
            name=user.username,
            avatar=user.avatar,
            email=user.userEmail,
        ).model_dump()
    return request_success(response_data)


def get_list(req: HttpRequest, list_name: str):
    if req.method != "GET":
        raise KeyError("Bad method", 400)
    friends = []
    user = User.objects.get(id=req.user_id)
    if list_name == "friend":
        for friendship in user.user1_friendships.all():
            if friendship.state == 1:
                friends.append(friendship.user2)
        for friendship in user.user2_friendships.all():
            if friendship.state == 1:
                friends.append(friendship.user1)
    elif list_name == "apply":
        for friendship in user.user2_friendships.all():
            if friendship.state == 0:
                friends.append(friendship.user1)
    elif list_name == "you_apply":
        for friendship in user.user1_friendships.all():
            if friendship.state == 0:
                friends.append(friendship.user2)
    else:
        raise KeyError("Bad list name(wrong in backend", 400)
    response_data = {
        "friends": [
            UserData(
                id=friend.id,
                name=friend.username,
                avatar=friend.avatar,
                email=friend.userEmail,
            ).model_dump()
            for friend in friends
        ]
    }
    return response_data


@csrf_exempt  # 允许跨域,便于测试
def get_friend_list(req: HttpRequest):
    try:
        response_data = get_list(req, "friend")
    except KeyError as e:
        error_message, status_code = str(e.args[0]), int(e.args[1])
        return request_failed(2, error_message, status_code=status_code)
    return request_success(response_data)


@csrf_exempt  # 允许跨域,便于测试
def get_apply_list(req: HttpRequest):
    try:
        response_data = get_list(req, "apply")
    except KeyError as e:
        error_message, status_code = str(e.args[0]), int(e.args[1])
        return request_failed(2, error_message, status_code=status_code)
    return request_success(response_data)


@csrf_exempt  # 允许跨域,便于测试
def get_you_apply_list(req: HttpRequest):
    try:
        response_data = get_list(req, "you_apply")
    except KeyError as e:
        error_message, status_code = str(e.args[0]), int(e.args[1])
        return request_failed(2, error_message, status_code=status_code)
    return request_success(response_data)


@csrf_exempt
def verification(signed_data):
    print("Your are in verification! ")
    data = loads(signed_data)
    user_id = data["user_id"]
    email = data["email"]
    print("1!")
    user = User.objects.get(id=user_id, userEmail=email, is_deleted=False)
    print("2")
    if user is None:
        print("3")
        return request_failed(2, "No such user in email verification!", status_code=401)
    else:
        print("user found!")
        user.verification = True
        user.save()
        return request_success()


@csrf_exempt
def sendemail(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD
    # 检查请求体
    use_id = req.user_id
    user = User.objects.get(id=use_id)
    email = user.userEmail
    email_sender(req, email, use_id)


@csrf_exempt
def avatar(req: HttpRequest, hash_code: str = None):
    if req.method == "POST":
        avatar_real = req.body
        # check the type
        mime = magic.Magic()
        detected_mime = mime.from_buffer(avatar_real)
        print(detected_mime)
        if "png" not in detected_mime.lower():
            return request_failed(2, "the file type is not correct", status_code=401)
        # get the md5
        md5_hash = hashlib.md5()
        md5_hash.update(avatar_real)
        real_md5 = md5_hash.hexdigest()
        # save the file
        if not os.path.exists("./files/avatar_storage"):
            os.mkdir("./files/avatar_storage")
        file_path = "./files/avatar_storage/" + real_md5
        if not os.path.exists(file_path):
            with open(file_path, "wb") as f:
                f.write(avatar_real)
        # save the file path
        user = User.objects.get(id=req.user_id)
        user.avatar = real_md5
        user.save()
        return request_success()
    elif req.method == "GET":
        user = User.objects.get(id=req.user_id)
        avatar_path = "./files/avatar_storage/" + user.avatar
        if hash_code:
            avatar_path = "./files/avatar_storage/" + hash_code
        if avatar_path is None:
            return request_failed(2, "the avatar is not exist", status_code=401)
        if not os.path.exists(avatar_path):
            return request_failed(2, "the avatar is not exist", status_code=401)
        with open(avatar_path, "rb") as f:
            avatar_real = f.read()
        response = HttpResponse(avatar_real, content_type="image/jpeg")
        return response


@csrf_exempt
def profile(req: HttpRequest):
    if req.method == "POST":
        user_id = req.user_id
        profile_get = json.loads(req.body)
        user = User.objects.get(id=user_id)
        user.profile = profile_get
        user.save()
        return request_success()
    elif req.method == "GET":
        user_id = req.user_id
        user = User.objects.get(id=user_id)
        user_profile = user.profile
        response_data = user_profile
        return request_success(response_data)


@csrf_exempt
def user_search(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD
    body = json.loads(req.body)
    user_message = require(
        body, "info", "string", err_msg="Missing or error type of [info]"
    )
    search_type = require(
        body, "type", "int", err_msg="Missing or error type of [type]"
    )
    user_list = []
    if search_type == 0:  # user_id
        if not User.objects.filter(id=user_message).exists():
            return request_failed(2, "User not exists", status_code=403)
        user = User.objects.get(id=user_message)
        user_list.append(user)
    elif search_type == 1:  # user_email
        user_list = User.objects.filter(userEmail__icontains=user_message)
        if len(user_list) == 0:
            return request_failed(2, "User not exists", status_code=403)
    elif search_type == 2:  # user_name
        user_list = User.objects.filter(username__icontains=user_message)
        if len(user_list) == 0:
            return request_failed(2, "User not exists", status_code=403)
    else:
        return BAD_METHOD
    response_data = {
        "users": [
            UserData(
                id=user.id,
                name=user.username,
                avatar=user.avatar,
                email=user.userEmail,
            ).model_dump()
            for user in user_list
        ]
    }
    return request_success(response_data)


@csrf_exempt
def delete_user(req: HttpRequest):
    session = SessionData(req)
    if session.user_id is None:
        return request_failed(2, "User isn't logging in! ", status_code=401)
    if req.method != "DELETE":
        return BAD_METHOD
    user = User.objects.get(id=session.user_id)
    # exception
    if user is None:
        return request_failed(2, "Deleting a user that doesn't exist!", status_code=401)
    else:
        session.user_id = None
        user.userEmail = user.userEmail + "is_deleted"
        user.is_deleted = True
        user.save()
        return request_success()
