import hashlib
import json
import os
import re
from telethu import settings 
import magic
from django.core.signing import loads
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from datetime import datetime
from users.email import email_sender
from users.models import User, GroupList, VerifyMailList, LoginMailList
from utils.data import UserData, GroupData
from utils.session import SessionData
from utils.uid import globalIdMaker
from utils.utils_jwt import hash_string_with_sha256, generate_jwt_token
from utils.utils_request import request_failed, request_success, BAD_METHOD
from utils.utils_require import check_require, require
import time

def authentication(req: HttpRequest):
    # 检查请求方法
    if req.method != "POST":
        raise KeyError("Bad method", 405)
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
        return request_failed(2, "Wrong password", status_code=403)
    user_id = user.id
    token = generate_jwt_token(user_id)
    session = SessionData(req)
    if session.user_id is not None:
        return request_failed(
            2,
            "Login failed because some user has login",
            status_code=403,
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
def login_with_email(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD
    body = json.loads(req.body)
    try:
        # Only receive email for verification
        user_email = require(
            body, "userEmail", "string", err_msg="Missing or error type of [email]"
        )
        new_password = require(
            body, "new_password", "string", err_msg="Missing or error type of [new_password]"
        )
        verification_code = require(
            body,
            "verification_code",
            "string",
            err_msg="Missing or error type of [verification_code]",
        )
    except KeyError as e:
        error_message, status_code = str(e.args[0]), int(e.args[1])
        return request_failed(2, error_message, status_code=status_code)
    
    verifier = VerifyMailList.objects.filter(email=user_email).first()

    if (verifier is None) or int(verifier.verification_code == 0):
        return request_failed(2, "Email haven't registered yet! ", status_code=404)
    print("now", time.time())
    print("verify at: ", verifier.verification_time / 1000000)
    if time.time() - (verifier.verification_time / 1000000) > 300:
        verifier.verification_code = 0
        verifier.verification_time = 0
        verifier.save()
        return request_failed(2, "Verification has expired!", status_code=403)
    if settings.DEBUG:
        if not (int(verification_code) == 114514 or int(verification_code) == verifier.verification_code):
            return request_failed(2, "Wrong verification code! ", status_code=404)
    else:
        if verifier.verification_code != int(verification_code):
            return request_failed(2, "Wrong verification code! ", status_code=404)
        
    # Change the password to the new password and login
    user = User.objects.get(userEmail=user_email)
    if user is None:
        return request_failed(2, "No such user! ")
    user.password = hash_string_with_sha256(new_password, num_iterations=5)
    user.save()
    user_id = user.id
    token = generate_jwt_token(user_id)
    session = SessionData(req)
    if session.user_id is not None:
        return request_failed(
            2,
            "Login failed because some user has login",
            status_code=403,
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
        return request_failed(2, "Logging out with the wrong user!", status_code=404)
    hashed_password = hash_string_with_sha256(password, num_iterations=5)
    if user.password != hashed_password:
        return request_failed(2, "Wrong password", status_code=404)
    loginwithmail = LoginMailList.objects.filter(email=user.userEmail).first()
    if loginwithmail is not None:
        loginwithmail.verification_code = 0
        loginwithmail.verification_time = 0
        loginwithmail.save()
    session = SessionData(req)
    session.user_id = None
    return request_success()


@csrf_exempt  # 允许跨域,便于测试
def receive_code(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD
    body = json.loads(req.body)
    try:
        # Only receive email for verification
        user_email = require(
            body, "userEmail", "string", err_msg="Missing or error type of [email]"
        )
    except KeyError as e:
        error_message, status_code = str(e.args[0]), int(e.args[1])
        return request_failed(2, error_message, status_code=status_code)
    if not check_require(user_email, "email"):
        return request_failed(2, "Invalid email", status_code=422)
    email_ret = email_sender(user_email, 0)
    if email_ret == 0:
        return request_failed(
            2, "Invalid email rejected by the email sender", status_code=422
        )
    # Get or create
    verify_maillist, created = VerifyMailList.objects.get_or_create(email=user_email)
    verify_maillist.verification_code = email_ret
    verify_maillist.verification_time = time.time() * 1000000
    verify_maillist.save()

    return request_success()


@csrf_exempt  # 允许跨域,便于测试
def register(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD
    body = json.loads(req.body)
    try:
        username = require(
            body, "userName", "string", err_msg="Missing or error type of [userName]"
        )
        password = require(
            body, "password", "string", err_msg="Missing or error type of [password]"
        )
        # Only receive email for verification
        user_email = require(
            body, "userEmail", "string", err_msg="Missing or error type of [email]"
        )
        verification_code = require(
            body,
            "verification_code",
            "string",
            err_msg="Missing or error type of [verification_code]",
        )
    except KeyError as e:
        error_message, status_code = str(e.args[0]), int(e.args[1])
        return request_failed(2, error_message, status_code=status_code)
    verifier = VerifyMailList.objects.filter(email=user_email).first()
    if User.objects.filter(userEmail=user_email, is_deleted=False).exists():
        return request_failed(2, "userEmail already exists", status_code=403)
    if (verifier is None) or int(verifier.verification_code == 0):
        return request_failed(2, "Email haven't registered yet! ", status_code=404)
    print("now", time.time())
    print("verify at: ", verifier.verification_time / 1000000)
    if time.time() - (verifier.verification_time / 1000000) > 300:
        verifier.verification_code = 0
        verifier.verification_time = 0
        verifier.save()
        return request_failed(2, "Verification has expired!", status_code=403)
    if settings.DEBUG:
        if not (int(verification_code) == 114514 or int(verification_code) == verifier.verification_code):
            return request_failed(2, "Wrong verification code! ", status_code=404)
    else:
        if verifier.verification_code != int(verification_code):
            return request_failed(2, "Wrong verification code! ", status_code=404)
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
    return request_success()


@require_GET
def get_user_info(req: HttpRequest, user_id: int):
    if req.method != "GET":
        return BAD_METHOD
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
                owner=None if group.group_owner is None else group.group_owner.id,
                admin=[admin.id for admin in group.group_admin.all()],
                top_message=[
                    message.message_id for message in group.group_top_message.all()
                ],
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
        for friendship in user.user2_friendships.all():
            if friendship.state == 2:
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
    response_data = {"list": [friend.id for friend in friends]}
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
        return request_failed(2, "No such user in email verification!", status_code=404)
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
    email_sender(email, 0)


@csrf_exempt
def avatar(req: HttpRequest, hash_code: str = None):
    if req.method == "POST":
        avatar_real = req.body
        # check the type
        mime = magic.Magic()
        detected_mime = mime.from_buffer(avatar_real)
        print(detected_mime)
        if "png" not in detected_mime.lower() and "jpeg" not in detected_mime.lower() and "jpg" not in detected_mime.lower():
            return request_failed(2, "the file type is not correct", status_code=406)
        # get the md5
        md5_hash = hashlib.md5()
        md5_hash.update(avatar_real)
        real_md5 = md5_hash.hexdigest()
        # save the file
        if not os.path.exists("./files/file_storage"):
            os.mkdir("./files/file_storage")
        file_path = "./files/file_storage/" + real_md5
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
        avatar_path = "./files/file_storage/" + user.avatar
        if hash_code:
            avatar_path = "./files/file_storage/" + hash_code
        if avatar_path is None:
            return request_failed(2, "the avatar is not exist", status_code=404)
        if not os.path.exists(avatar_path):
            return request_failed(2, "the avatar is not exist", status_code=404)
        with open(avatar_path, "rb") as f:
            avatar_real = f.read()
        # check the type
        mime = magic.Magic()
        detected_mime = mime.from_buffer(avatar_real)
        if "jpeg" in detected_mime.lower():
            response = HttpResponse(avatar_real, content_type="image/jpeg")
        elif "png" in detected_mime.lower():
            response = HttpResponse(avatar_real, content_type="image/png")
        elif "jpg" in detected_mime.lower():
            response = HttpResponse(avatar_real, content_type="image/jpg")
        else:
            return request_failed(2, "the file type is not correct", status_code=404)
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
        return JsonResponse(response_data)


@csrf_exempt
def user_search(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD
    body = json.loads(req.body)
    user_message = require(
        body, "info", "string", err_msg="Missing or error type of [info]"
    )
    # 用正则表达式匹配info内容，如果是数字，type就是0，如果是邮箱，type就是1，如果是用户名，type就是2
    pattern0 = re.compile(r"^[0-9]*$")
    pattern1 = re.compile(r"^[a-zA-Z0-9_-]+@[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)+$")
    if pattern0.match(user_message):
        search_type = 0
    elif pattern1.match(user_message):
        search_type = 1
    else:
        search_type = 2
    user_list = []
    id_list = []
    if search_type == 0:  # user_id,只有全为数字才能这么搜
        user_id = int(user_message)
        if User.objects.filter(id=user_id).exists():
            user = User.objects.filter(id=user_id).first()
            id_list = [user]
    email_list = User.objects.filter(userEmail__icontains=user_message)
    name_list = User.objects.filter(username__icontains=user_message)
    if search_type == 0:
        user_list.extend(id_list)
        user_list.extend(email_list)
        user_list.extend(name_list)
    elif search_type == 1:
        user_list.extend(email_list)
        user_list.extend(name_list)
    else:
        user_list.extend(name_list)
        user_list.extend(email_list)
    user_data = []
    for user in user_list:  # 去重
        if user not in user_data:
            user_data.append(user)
    response_data = {
        "users": list(
            [
                UserData(
                    id=user.id,
                    name=user.username,
                    avatar=user.avatar,
                    email=user.userEmail,
                ).model_dump()
                for user in user_data
            ]
        )
    }
    return request_success(response_data)


@csrf_exempt
def delete_user(req: HttpRequest):
    if req.method != "DELETE":
        return BAD_METHOD
    user = User.objects.get(id=req.user_id)
    # exception
    if user is None:
        return request_failed(2, "Deleting a user that doesn't exist!", status_code=404)
    else:
        body = json.loads(req.body)
        password = body.get("password")
        if password is None:
            return request_failed(2, "Password missing! ", status_code=403)
        hashed_password = hash_string_with_sha256(password, num_iterations=5)
        if user.password != hashed_password:
            return request_failed(2, "Wrong password", status_code=403)
        email = user.userEmail
        user.userEmail = user.userEmail + "is_deleted"
        current_time = datetime.now()
        time_string = current_time.strftime("%Y-%m-%d %H:%M:%S")
        user.userEmail = user.userEmail + time_string
        user.is_deleted = True
        user.save()
        verifier = VerifyMailList.objects.filter(email=email).first()
        if verifier is None:
            return request_failed(2, "Not in verificaition list!", status_code=404)
        verifier.verification_code = 0
        verifier.save()
        loginwithmail = LoginMailList.objects.filter(email=user.userEmail).first()
        if loginwithmail is not None:
            loginwithmail.verification_code = 0
            loginwithmail.verification_time = 0
            loginwithmail.save()
        return request_success()


@csrf_exempt
def block_user_list(req: HttpRequest):
    if req.method != "GET":
        return BAD_METHOD
    user = User.objects.get(id=req.user_id)
    block_list = []
    for friendship in user.user1_friendships.all():
        if friendship.state == 2:
            block_list.append(friendship.user2.id)
    response = {"block_list": block_list}
    return JsonResponse(response)


@csrf_exempt
def edit_profile(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD
    user = get_object_or_404(User, id=req.user_id)
    body = json.loads(req.body)
    new_name = body.get("name")
    new_email = body.get("email")
    new_password = body.get("new_password")
    old_password = body.get("old_password")
    token = ""
    if new_email:
        password = body.get("password")
        if password is None:
            return request_failed(2, "Password not found for altering email!", status_code=403)
        password = hash_string_with_sha256(password, num_iterations=5)
        if user.password != password:
            return request_failed(2, "Incorrect password! ", status_code=403)
        verification_code = require(
            body,
            "verification_code",
            "string",
            err_msg="Missing or error type of [verification_code]",
        )
        verifier = VerifyMailList.objects.filter(email=new_email).first()
        if verifier is None:
            return request_failed(2, "Not in verificaition list!", status_code=404)
        if not (settings.DEBUG and int(verification_code) == 114514) and verifier.verification_code != int(verification_code):
            return request_failed(2, "Wrong verification code! ", status_code=404)
        if User.objects.filter(userEmail=new_email).exists():
            return request_failed(2, "New email already exists! ", status_code=404)
        user = User.objects.filter(id=req.user_id).first()
        if user is None:
            return request_failed(2, "No user found! ", status_code=404)
        verifier.email = new_email
        verifier.verification_code = 0
        verifier.verification_time = 0
        verifier.save()
        user.userEmail = new_email
        user.save()
    if new_name:
        user.username = new_name
    if new_password:
        print("user: ", user.password)
        print("old: ", hash_string_with_sha256(old_password, num_iterations=5))
        if not old_password:
            return request_failed(2, "Old password not provided", 403)
        if not user.password == hash_string_with_sha256(old_password, num_iterations=5):
            return request_failed(2, "Wrong password", 403)
        user.password = hash_string_with_sha256(new_password, num_iterations=5)
        user_id = user.id
        token = generate_jwt_token(user_id)
    user.save()
    return JsonResponse(
        {
            "id": user.id,
            "name": user.username,
            "email": user.userEmail,
            "avatar": user.avatar,
            "token": token
        }
    )


@csrf_exempt
def email_exists(req: HttpRequest, query_email: str):
    if req.method != "GET":
        return BAD_METHOD
    exists = User.objects.filter(userEmail=query_email).exists()
    return HttpResponse(exists)


@csrf_exempt
def group_candidates(req: HttpRequest, group_id: int):
    if req.method != "GET":
        return BAD_METHOD
    user = User.objects.get(id=req.user_id)
    if user is None:
        return request_failed(2, "User not found!", status_code=404)
    group = GroupList.objects.get(group_id=group_id)
    if group is None:
        return request_failed(2, "Group not found!", status_code=404)
    # if you are not the owner or admin, you can't get the candidates
    if user != group.group_owner and user not in group.group_admin.all():
        return request_failed(2, "You are not the owner or admin!", status_code=403)
    candidates = []
    for candidate in group.group_candidate_members.all():
        candidates.append(candidate.id)
    response = {"candidates": candidates}
    return JsonResponse(response)
