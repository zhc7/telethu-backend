from django.shortcuts import render
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from utils.utils_require import check_require, CheckRequire, require
import json
from users.models import User, Friendship
from utils.utils_request import request_failed, request_success, BAD_METHOD




# Create your views here.
@CheckRequire
@csrf_exempt  # 关闭csrf验证
def login(req: HttpRequest):
    # 检查请求方法
    if req.method != 'POST':
        return BAD_METHOD
    # 检查请求体
    body = json.loads(req.body)
    username = require(body, "userName", "string", err_msg="Missing or error type of [userName]")
    password = require(body, "password", "string", err_msg="Missing or error type of [password]")
    # 检查用户名是否存在
    if not User.objects.filter(username=username).exists():
        return request_failed(2, "Username not exists", status_code=401)
    # 检查密码是否正确
    user = User.objects.get(username=username)
    if user.password != password:
        return request_failed(2, "Wrong password", status_code=401)
    # 生成token
    token = user.generate_token()
    # 返回token
    return request_success({
        "token": token
    })


@CheckRequire
@csrf_exempt  # 关闭csrf验证
def logout(req: HttpRequest):
    # 检查请求方法
    if req.method != 'POST':
        return BAD_METHOD
    # 检查请求头
    if not "HTTP_AUTHORIZATION" in req.META:
        return request_failed(2, "Missing authorization header", status_code=401)
    # 检查用户是否存在
    token = req.META["HTTP_AUTHORIZATION"]
    if not User.objects.filter(token=token).exists():
        return request_failed(2, "User not exists", status_code=401)
    # 清除token
    user = User.objects.get(token=token)
    user.token = None
    user.save()
    return request_success()


@CheckRequire
@csrf_exempt  # 允许跨域,便于测试
def register(req: HttpRequest):
    # 检查请求方法
    if req.method != 'POST':
        return BAD_METHOD
    # 检查请求体
    body = json.loads(req.body)
    username = require(body, "userName", "string", err_msg="Missing or error type of [userName]")
    password = require(body, "password", "string", err_msg="Missing or error type of [password]")
    # phone = require(body, "phone", "string", err_msg="Missing or error type of [phone]")
    # 检查用户名是否已存在
    if User.objects.filter(username=username).exists():
        return request_failed(2, "Username already exists", status_code=401)
    # 检查用户名格式，密码格式，手机号格式,如果不符合要求，返回422.有需求改变取check_require函数去改动
    if not check_require(username, "username"):
        return request_failed(2, "Invalid username", status_code=422)
    if not check_require(password, "password"):
        return request_failed(2, "Invalid password", status_code=422)
    # if not check_require (phone, "phone"):
    #    return request_failed(2, "Invalid phone", status_code=422)
    # 发送手机验证码进行验证
    # if not send_sms(phone):
    #    return request_failed(2, "Failed to send SMS", status_code=500)
    # 创建用户
    user = User(username=username, password=password)
    user.save()
    return request_success()

# 用户好友管理
def check_friend_request(req: HttpRequest):
    # 检查请求方法
    if req.method != 'POST':
        return JsonResponse({"code": 2, "info": "Bad method"}, status=400)

    # 检查请求头
    if "HTTP_AUTHORIZATION" not in req.META:
        return JsonResponse({"code": 2, "info": "Missing authorization header"}, status=401)

    # 检查请求体
    try:
        body = json.loads(req.body)
        friend_id = int(body.get("friendId", 0))  # 将friend_id转换为整数
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"code": 2, "info": "Missing or error type of 'friendId'"}, status=400)

    # 检查用户是否存在
    token = req.META["HTTP_AUTHORIZATION"]
    if not User.objects.filter(token=token).exists():
        return JsonResponse({"code": 2, "info": "User not exists"}, status=401)

    # 检查好友是否存在
    if not User.objects.filter(id=friend_id).exists():
        return JsonResponse({"code": 2, "info": "Friend not exists"}, status=401)

    # 如果没有错误，返回 None
    return None


@CheckRequire
@csrf_exempt  # 允许跨域,便于测试
def apply_friend(req: HttpRequest):
    # 基本检查
    error = check_friend_request(req)
    if error is not None:
        return error
    # 检查
    token = req.META["HTTP_AUTHORIZATION"]
    body = json.loads(req.body)
    friend_id = int(body.get("friendId", 0))  # 将friend_id转换为整数
    user = User.objects.get(token=token)
    friend = User.objects.get(id=friend_id)
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
    friend_id = 0
    error = check_friend_request(req)
    if error is not None:
        return error
    # 检查
    token = req.META["HTTP_AUTHORIZATION"]
    body = json.loads(req.body)
    friend_id = int(body.get("friendId", 0))  # 将friend_id转换为整数
    user = User.objects.get(token=token)
    friend = User.objects.get(id=friend_id)
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
    friend_id = 0
    error = check_friend_request(req)
    if error is not None:
        return error
    # 检查
    token = req.META["HTTP_AUTHORIZATION"]
    body = json.loads(req.body)
    friend_id = int(body.get("friendId", 0))  # 将friend_id转换为整数
    user = User.objects.get(token=token)
    friend = User.objects.get(id=friend_id)
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
    friend_id = 0
    error = check_friend_request(req)
    if error is not None:
        return error
    # 检查
    token = req.META["HTTP_AUTHORIZATION"]
    body = json.loads(req.body)
    friend_id = int(body.get("friendId", 0))  # 将friend_id转换为整数
    user = User.objects.get(token=token)
    friend = User.objects.get(id=friend_id)
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
    friend_id = 0
    error = check_friend_request(req)
    if error is not None:
        return error
    # 检查
    token = req.META["HTTP_AUTHORIZATION"]
    body = json.loads(req.body)
    friend_id = int(body.get("friendId", 0))  # 将friend_id转换为整数
    user = User.objects.get(token=token)
    friend = User.objects.get(id=friend_id)
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
    friend_id = 0
    error = check_friend_request(req)
    if error is not None:
        return error
    # 检查
    token = req.META["HTTP_AUTHORIZATION"]
    body = json.loads(req.body)
    friend_id = int(body.get("friendId", 0))  # 将friend_id转换为整数
    user = User.objects.get(token=token)
    friend = User.objects.get(id=friend_id)
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
