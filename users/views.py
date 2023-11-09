import hashlib
import json
import os
from django.http import HttpRequest, JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from users.models import User, Friendship
from utils.data import UserData
from users.email import email_sender
from utils.session import SessionData
from utils.uid import globalIdMaker
from utils.utils_jwt import hash_string_with_sha256, generate_jwt_token
from utils.utils_request import request_failed, request_success, BAD_METHOD
from utils.utils_require import check_require, CheckRequire, require
from django.core.signing import loads
import magic


# Create your views here.
@CheckRequire
@csrf_exempt  # 关闭csrf验证
def login(req: HttpRequest):
    # TODO：登陆方式改为邮箱登录
    # 检查请求方法
    if req.method != "POST":
        return BAD_METHOD

    # 检查请求体
    body = json.loads(req.body)
    password = require(
        body, "password", "string", err_msg="Missing or error type of [password]"
    )
    user_email = require(
        body, "userEmail", "string", err_msg="Missing or error type of [email]"
    )

    # 检查用户名是否存在
    if not User.objects.filter(userEmail=user_email).exists():
        return request_failed(2, "Username not exists", status_code=401)

    # 检查密码是否正确
    user = User.objects.get(userEmail=user_email)

    # 利用 SHA256 算法对用户输入的密码进行 5 次加密，与正确的密码（同样已经加密 5 次）进行对比
    hashed_password = hash_string_with_sha256(password, num_iterations=5)
    if user.password != hashed_password:
        return request_failed(2, "Wrong password", status_code=401)
    user_id = user.id
    # 生成token
    token = generate_jwt_token(user_id)
    # 这个生成的 Token 保证了安全性：其 payload 当中只有 userName 字段，并不含有密码。因此黑客即使截获了 JWT token 之后也无法
    # 获取登录所需的全部信息。在需要判断用户是否存在的场合，具体实现机制如下：从 JWT Token 的字段当中获得 userName 字段，并利用该
    # 字段去 User 数据库当中获得 userEmail=email的用户，如果存在，则说明用户存在，否则说明用户不存在。

    # TODO：
    session = SessionData(req)
    if session.user_id is not None:
        return request_failed(
            2,
            f"Login failed because user {session.user_id} has login",
            status_code=401,
        )
    session.user_id = user_id
    # 首先判断 session.user_email 是否为空，如果不为空，则拒 login 请求

    # 返回token, 以及通过 is_login 判断这是登录请求
    response_data = {
        "token": token,
        "user": UserData(
            id=user.id, name=user.username, avatar=user.avatar, email=user.userEmail
        ).model_dump(),
    }
    return request_success(response_data)


@CheckRequire
@csrf_exempt  # 关闭csrf验证
def logout(req: HttpRequest):
    # 检查请求方法
    if req.method != "POST":
        return BAD_METHOD

    # 检查用户是否存在
    body = json.loads(req.body)
    password = require(
        body, "password", "string", err_msg="Missing or error type of [password]"
    )
    user_email = require(
        body, "userEmail", "string", err_msg="Missing or error type of [email]"
    )
    if not User.objects.filter(userEmail=user_email).exists():
        return request_failed(2, "Username not exists", status_code=401)
    user = User.objects.get(userEmail=user_email)
    user_id = user.id
    session = SessionData(req)
    if user_id != session.user_id:
        return request_failed(2, "Logging out with the wrong user!", status_code=401)
    hashed_password = hash_string_with_sha256(password, num_iterations=5)
    if user.password != hashed_password:
        return request_failed(2, "Wrong password", status_code=401)
    # 在 logout 的时候需要将 session 的 user 字段置空

    session = SessionData(req)
    session.user_id = None
    return request_success()


@CheckRequire
@csrf_exempt  # 允许跨域,便于测试
def register(req: HttpRequest):
    # 检查请求方法
    if req.method != "POST":
        return BAD_METHOD
    # 检查请求体
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
    print("user_email is: ", user_email)
    # phone = require(body, "phone", "string", err_msg="Missing or error type of [phone]")
    # 检查用户邮箱是否已存在
    if User.objects.filter(userEmail=user_email).exists():
        return request_failed(2, "userEmail already exists", status_code=401)

    # 检查用户名格式，密码格式，手机号格式,如果不符合要求，返回422.有需求改变取check_require函数去改动
    if not check_require(username, "username"):
        return request_failed(2, "Invalid username", status_code=422)
    if not check_require(password, "password"):
        return request_failed(2, "Invalid password", status_code=422)
    if not check_require(user_email, "email"):
        return request_failed(2, "Invalid email", status_code=422)

    # if not check_require (phone, "phone"):
    #    return request_failed(2, "Invalid phone", status_code=422)
    # 发送手机验证码进行验证
    # if not send_sms(phone):
    #    return request_failed(2, "Failed to send SMS", status_code=500)
    # 创建用户

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


# 用户好友管理
def check_friend_request(req: HttpRequest):
    # 检查请求方法
    if req.method != "POST":
        return JsonResponse({"code": 2, "info": "Bad method"}, status=400)
    # 检查请求体与好友是否存在
    try:
        body = json.loads(req.body)
        friend_id = int(body.get("friendId", 0))  # 将friend_id转换为整数
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {"code": 2, "info": "Missing or error type of 'friendId'"}, status=400
        )
    if not User.objects.filter(id=friend_id).exists():
        return JsonResponse({"code": 2, "info": "Friend not exists"}, status=401)

    # 如果没有错误，返回 None
    return None


# 用于获得用户和好友的函数
def get_user_and_friend(req: HttpRequest):  # 获得好友列表
    # 获得users
    user = User.objects.get(id=req.user_id)
    # 获得friend
    body = json.loads(req.body)
    friend_id = int(body.get("friendId", 0))  # 将friend_id转换为整数
    friend = User.objects.get(id=friend_id)
    return user, friend


@CheckRequire
@csrf_exempt  # 允许跨域,便于测试
def apply_friend(req: HttpRequest):
    # 基本检查
    error = check_friend_request(req)
    if error is not None:
        return error
    # 检查
    user, friend = get_user_and_friend(req)
    friendship = None
    # 排除自我添加
    if user.id == friend.id:
        return request_failed(2, "Cannot add yourself", status_code=401)
    # 检查是否已经是好友
    if user.user1_friendships.filter(user2=friend).exists():
        friendship = user.user1_friendships.get(user2=friend)
    elif user.user2_friendships.filter(user1=friend).exists():
        friendship = user.user2_friendships.get(user1=friend)
    if friendship is not None:
        if friendship.state == 1:
            return request_failed(2, "Already friends", status_code=401)
        elif friendship.state == 0 and friendship.user1 == user:
            return request_failed(2, "Already sent request", status_code=401)
        elif friendship.state == 0 and friendship.user2 == user:
            return request_failed(2, "Already received request", status_code=401)
        elif friendship.state == 2:
            return request_failed(2, "Already blocked", status_code=401)
        elif friendship.state == 3:
            friendship.user1 = user
            friendship.user2 = friend
            friendship.state = 0
            return request_success()
    # 创建好友关系
    friendship = Friendship(user1=user, user2=friend, state=0)
    friendship.save()
    return request_success()


@CheckRequire
@csrf_exempt  # 允许跨域,便于测试
def accept_friend(req: HttpRequest):
    # 基本检查
    error = check_friend_request(req)
    if error is not None:
        return error
    # 检查
    user, friend = get_user_and_friend(req)
    friendship = None
    # 排除自我添加
    if user.id == friend.id:
        return request_failed(2, "Cannot add yourself", status_code=401)
    # 检查是否已经是好友
    if user.user1_friendships.filter(user2=friend).exists():
        friendship = user.user1_friendships.get(user2=friend)
    elif user.user2_friendships.filter(user1=friend).exists():
        friendship = user.user2_friendships.get(user1=friend)
    if friendship is None:
        return request_failed(2, "Not friends send request", status_code=401)
    elif friendship.state == 1:
        return request_failed(2, "Already friends", status_code=401)
    elif friendship.state == 2:
        return request_failed(2, "Already blocked", status_code=401)
    elif friendship.state == 3:
        return request_failed(2, "Already rejected", status_code=401)
    elif friendship.state == 0 and friendship.user1 == user:
        return request_failed(2, "Already sent request", status_code=401)
    elif friendship.state == 0 and friendship.user1 != user:
        friendship.state = 1
        friendship.save()
        return request_success()


@CheckRequire
@csrf_exempt  # 允许跨域,便于测试
def reject_friend(req: HttpRequest):
    # 基本检查
    error = check_friend_request(req)
    if error is not None:
        return error
    # 检查
    user, friend = get_user_and_friend(req)
    friendship = None
    # 排除自我添加
    if user.id == friend.id:
        return request_failed(2, "Cannot add yourself", status_code=401)
    # 检查是否已经是好友
    if user.user1_friendships.filter(user2=friend).exists():
        friendship = user.user1_friendships.get(user2=friend)
    elif user.user2_friendships.filter(user1=friend).exists():
        friendship = user.user2_friendships.get(user1=friend)
    if friendship is None:
        return request_failed(2, "Not friends send request", status_code=401)
    elif friendship.state == 1:
        return request_failed(2, "Already friends", status_code=401)
    elif friendship.state == 2:
        return request_failed(2, "Already blocked", status_code=401)
    elif friendship.state == 3:
        return request_failed(2, "Already rejected", status_code=401)
    elif friendship.state == 0 and friendship.user1 == user:
        return request_failed(2, "You sent request", status_code=401)
    elif friendship.state == 0 and friendship.user2 == user:
        friendship.state = 3
        friendship.user1 = user
        friendship.user2 = friend
        friendship.save()
        return request_success()


@CheckRequire
@csrf_exempt  # 允许跨域,便于测试
def block_friend(req: HttpRequest):
    # 基本检查
    error = check_friend_request(req)
    if error is not None:
        return error
    # 检查
    user, friend = get_user_and_friend(req)
    friendship = None
    # 排除自我添加
    if user.id == friend.id:
        return request_failed(2, "Cannot add yourself", status_code=401)
    # 检查是否已经是好友
    if user.user1_friendships.filter(user2=friend).exists():
        friendship = user.user1_friendships.get(user2=friend)
    elif user.user2_friendships.filter(user1=friend).exists():
        friendship = user.user2_friendships.get(user1=friend)
    if friendship is None:
        friendship = Friendship(user1=user, user2=friend, state=2, initiator=user)
        friendship.save()
        return request_success()
    elif friendship is not None:
        friendship.state = 2
        friendship.user1 = user
        friendship.user2 = friend
        friendship.save()
        return request_success()


@CheckRequire
@csrf_exempt  # 允许跨域,便于测试
def unblock_friend(req: HttpRequest):
    # 基本检查
    error = check_friend_request(req)
    if error is not None:
        return error
    # 检查
    user, friend = get_user_and_friend(req)
    friendship = None
    # 排除自我添加
    if user.id == friend.id:
        return request_failed(2, "Cannot add yourself", status_code=401)
    # 检查是否已经是好友
    if user.user1_friendships.filter(user2=friend).exists():
        friendship = user.user1_friendships.get(user2=friend)
    elif user.user2_friendships.filter(user1=friend).exists():
        friendship = user.user2_friendships.get(user1=friend)
    if friendship is None:
        return request_failed(2, "Not friends", status_code=401)
    elif friendship.state == 2:  # 删除这一列就不是拉黑了
        friendship.delete()
        return request_success()
    elif friendship.state != 2:
        return request_failed(2, "Not blocked", status_code=401)


@CheckRequire
@csrf_exempt  # 允许跨域,便于测试
def delete_friend(req: HttpRequest):
    # 基本检查
    error = check_friend_request(req)
    if error is not None:
        return error
    # 检查
    user, friend = get_user_and_friend(req)
    friendship = None
    # 排除自我添加
    if user.id == friend.id:
        return request_failed(2, "Cannot add yourself", status_code=401)
    # 检查是否已经是好友
    if user.user1_friendships.filter(user2=friend).exists():
        friendship = user.user1_friendships.get(user2=friend)
    elif user.user2_friendships.filter(user1=friend).exists():
        friendship = user.user2_friendships.get(user1=friend)
    if friendship is None:
        return request_failed(2, "Not friends", status_code=401)
    elif friendship.state == 1:
        friendship.delete()
        return request_success()
    elif friendship.state != 1:
        return request_failed(2, "Not friends", status_code=401)


@CheckRequire
@csrf_exempt  # 允许跨域,便于测试
def get_friend_list(req: HttpRequest):
    # 检查请求方法
    if req.method != "GET":
        return BAD_METHOD
    # 检查请求头
    # 从 JWT 当中获得用户名是否存在，并利用获得的用户名进入
    # 找出所有的friend
    friends = []
    user = User.objects.get(id=req.user_id)
    for friendship in user.user1_friendships.all():
        if friendship.state == 1:
            friends.append(friendship.user2)
    for friendship in user.user2_friendships.all():
        if friendship.state == 1:
            friends.append(friendship.user1)
    # 返回friend列表,包括friend的id,username,avatar
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
    return request_success(response_data)


@CheckRequire
@csrf_exempt  # 允许跨域,便于测试
def get_apply_list(req: HttpRequest):
    # 检查请求方法
    if req.method != "GET":
        return BAD_METHOD
    # 检查请求头
    # 从 JWT 当中获得用户名是否存在，并利用获得的用户名进入
    # 找出所有的friend
    friends = []
    user = User.objects.get(id=req.user_id)
    # for friendship in user.user1_friendships.all():
    #     if friendship.state == 0:
    #         friends.append(friendship.user2)
    for friendship in user.user2_friendships.all():
        if friendship.state == 0:
            friends.append(friendship.user1)
    # 返回friend列表,包括friend的id,username,avatar
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
    return request_success(response_data)


@CheckRequire
@csrf_exempt  # 允许跨域,便于测试
def get_you_apply_list(req: HttpRequest):
    # 检查请求方法
    if req.method != "GET":
        return BAD_METHOD
    # 检查请求头
    # 从 JWT 当中获得用户名是否存在，并利用获得的用户名进入
    # 找出所有的friend
    friends = []
    user = User.objects.get(id=req.user_id)
    for friendship in user.user1_friendships.all():
        if friendship.state == 0:
            friends.append(friendship.user2)
    # for friendship in user.user2_friendships.all():
    #     if friendship.state == 0:
    #         friends.append(friendship.user1)
    # 返回friend列表,包括friend的id,username,avatar
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
    return request_success(response_data)


@CheckRequire
@csrf_exempt
def verification(req: HttpRequest, signed_data):
    print("Your are in verification! ")
    data = loads(signed_data)
    user_id = data["user_id"]
    email = data["email"]
    print("1!")
    user = User.objects.get(id=user_id, userEmail=email)
    print("2")
    if user is None:
        print("3")
        return request_failed(2, "No such user in email verification!", status_code=401)
    else:
        print("user found!")
        user.verification = True
        user.save()
        return request_success()


@CheckRequire
@csrf_exempt
def sendemail(req: HttpRequest):
    if req.method != "POST":
        return BAD_METHOD

    # 检查请求体
    id = req.user_id
    user = User.objects.get(id=id)
    email = user.userEmail
    email_sender(req, email, id)


@CheckRequire
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
        user.avatar = file_path
        user.save()
        return request_success()
    elif req.method == "GET":
        user = User.objects.get(id=req.user_id)
        avatar_path = user.avatar
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


@CheckRequire
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
        profile = user.profile
        response_data = profile
        return request_success(response_data)


@CheckRequire
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
    if search_type == 0:  # user_id
        if not User.objects.filter(id=user_message).exists():
            return request_failed(2, "User not exists", status_code=403)
        user = User.objects.get(id=user_message)
        response_data = {
            "user": UserData(
                id=user.id,
                name=user.username,
                avatar=user.avatar,
                email=user.userEmail,
            ).model_dump()
        }
        return request_success(response_data)
    elif search_type == 1:  # user_email
        if not User.objects.filter(userEmail=user_message).exists():
            return request_failed(2, "User not exists", status_code=403)
        user = User.objects.get(userEmail=user_message)
        response_data = {
            "user": UserData(
                id=user.id,
                name=user.username,
                avatar=user.avatar,
                email=user.userEmail,
            ).model_dump()
        }
        return request_success(response_data)
    else:
        return BAD_METHOD
