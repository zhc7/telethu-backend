import json

from django.http import HttpRequest
from django.views.decorators.csrf import csrf_exempt

from users.models import User
from utils.session import SessionData
from utils.utils_jwt import hash_string_with_sha256, generate_jwt_token
from utils.utils_request import request_failed, request_success, BAD_METHOD
from utils.utils_require import check_require, CheckRequire, require


# Create your views here.
@CheckRequire
@csrf_exempt  # 关闭csrf验证
def login(req: HttpRequest):
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

    # 检查用户名是否存在
    if not User.objects.filter(username=username).exists():
        return request_failed(2, "Username not exists", status_code=401)

    # 检查密码是否正确
    user = User.objects.get(username=username)

    # 利用 SHA256 算法对用户输入的密码进行 5 次加密，与正确的密码（同样已经加密 5 次）进行对比
    hashed_password = hash_string_with_sha256(password, num_iterations=5)
    if user.password != hashed_password:
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
    if req.method != "POST":
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

    # 利用 SHA256 算法对新建用户的密码进行 5 次加密
    hashed_password = hash_string_with_sha256(password, num_iterations=5)
    user = User(username=username, password=hashed_password)
    user.save()
    return request_success()
