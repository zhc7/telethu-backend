from datetime import datetime

from django.shortcuts import redirect
from django.urls import reverse
from users.models import User
from utils.session import SessionData
from utils.utils_jwt import check_jwt_token
from utils.utils_request import request_failed
from django.http import HttpRequest, JsonResponse

# TODO: 在中间件中编写获得 id（ django-session，触发 session 机制可以自动获得 session_data ）


# TODO: 4 种比较情况：
# Token && Session: 先检查JWT是否合法，再检验二者的姓名部分是否一致, 并且对于 Session 方面进行检验
# Token && !Session: 添加相应的 Session （username， last_login）
# !Token && Session: pass
# else: redirect 到 login


class SimpleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    @staticmethod
    def add_login_time(request):
        session = SessionData(request)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session.last_login = current_time
        print("last_login at: ", session.last_login)

    # 在发送请求的时候，通过当前时间和 session 当中已经加入的 “last_login” 字段进行比较，如果超过一天就重定向到 login
    @staticmethod
    def check_last_login(request):
        current_time = datetime.now()
        session = SessionData(request)
        print("session is: ", dict(request.session.items()))
        last_login = session.last_login
        print("last_login is: ", last_login)
        if last_login:
            last_login_time = datetime.strptime(last_login, "%Y-%m-%d %H:%M:%S")
            time_difference = current_time - last_login_time
            if time_difference.days > 0:
                print("last login is one day ago!")
                return None
        else:
            # 如果 last_login 不存在，可能是用户尚未登录，也可以进行重定向
            print("no last login!")
            print("session: ", session)
            return None
        return 0

    # 除了利用 session 进行鉴权以外，还需要使用 request 当中的 JWT 进行鉴权
    @staticmethod
    def check_token(request):
        jwt_token = request.headers.get("Authorization")
        check_result = check_jwt_token(jwt_token)
        print("check_result is ", check_result)
        if check_result is not None:
            # 从 payload 当中获得 username 字段
            user_id = check_result["user_id"]
            users = User.objects.filter(id=user_id)
            if len(users) == 0:
                # 没有找到相应的 user
                return 0

        else:
            return 1

        if check_result["user_id"] != request.session.get("user_id"):
            return 2

    # 完整的鉴权逻辑，在上面的注释当中有所提及
    def check_token_and_session(self, request):
        token = request.headers.get("Authorization")
        if token and request.session:
            print("branch 1")
            token_result = self.check_token(request)
            if token_result == 0:
                return JsonResponse({"code": 2, "info": "User not found"}, status=401)
            elif token_result == 1:
                return request_failed(
                    2, "JWT not found or JWT format error", status_code=401
                )
            elif token_result == 2:
                if request.session.get("user_id") is None:
                    return request_failed(2, "Login has expired or haven't login!", status_code=401)
                return request_failed(
                    2,
                    "User id in session and token doesn't match! ",
                    status_code=401,
                )
            login_result = self.check_last_login(request)
            if login_result is None:
                return request_failed(2, "Login has expired or haven't login!", status_code=401)
        elif token and not request.session:
            print("branch 2")
            check_result = check_jwt_token(token)
            session = SessionData(request)
            if check_result is None:
                return request_failed(2, "Invalid or expired JWT", status_code=401)
            else:
                session.user_id = check_result["user_id"]
        elif not token and request.session:
            print("branch 3")
            if request.session.get("user_id") is None:
                return request_failed(2, "Login has expired or haven't login!", status_code=401)
            login_result = self.check_last_login(request)
            if login_result is None:
                return request_failed(2, "Login has expired or haven't login!", status_code=401)
        else:
            print("branch 4")
            return request_failed(2, "Can't find session and token!", status_code=401)
        session = SessionData(request)
        request.user_id = session.user_id
        return 0

    # 在收到 response 的时候，我们是不是应该做些什么...

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        # 现在之对于 request 进行处理
        path = request.path
        print("In auth middleware!")
        if not path.endswith("/login") and not path.endswith("/register"):
            print("You are not logging in!")
            result = self.check_token_and_session(request)
            if result != 0:
                return result

        response = self.get_response(request)
        # Code to be executed for each request/response after
        # the view is called.
        if path.endswith("/login"):
            print("You are now logging in! ")
            self.add_login_time(request)
        print("Out of auth middleware!")
        return response
