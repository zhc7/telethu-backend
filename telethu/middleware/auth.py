from datetime import datetime

from django.shortcuts import redirect
from django.urls import reverse

from utils.session import SessionData
from utils.utils_jwt import check_jwt_token
from utils.utils_request import request_failed


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

    # 在发送请求的时候，通过当前时间和 session 当中已经加入的 “last_login” 字段进行比较，如果超过一天就重定向到 login
    @staticmethod
    def check_last_login(request):
        current_time = datetime.now()
        session = SessionData(request)
        last_login = session.last_login
        if last_login:
            last_login_time = datetime.strptime(last_login, "%Y-%m-%d %H:%M:%S")
            time_difference = current_time - last_login_time
            if time_difference.days > 0:
                return redirect(reverse("login"))
        else:
            # 如果 last_login 不存在，可能是用户尚未登录，也可以进行重定向
            return redirect(reverse("login"))

    # 除了利用 session 进行鉴权以外，还需要使用 request 当中的 JWT 进行鉴权
    @staticmethod
    def check_token(request):
        jwt_token = request.headers.get("Authorization")
        check_result = check_jwt_token(jwt_token)
        if check_result is None:
            return request_failed(
                2, "JWT not found or JWT format error", status_code=401
            )

        if check_result["userEmail"] != request.session.get("userEmail"):
            return request_failed(2, "Wrong user userEmail", status_code=401)

    # 完整的鉴权逻辑，在上面的注释当中有所提及
    def check_token_and_session(self, request):
        jwt_token = request.headers.get("Authorization")
        if jwt_token and request.session:
            self.check_token(request)
            self.check_last_login(request)
        elif jwt_token and not request.session:
            check_result = check_jwt_token(jwt_token)
            session = SessionData(request)
            if check_result is None:
                return request_failed(2, "Invalid or expired JWT", status_code=401)
            else:
                session.username = check_result["userEmail"]
        elif not jwt_token and request.session:
            self.check_last_login(request)
        else:
            return redirect(reverse("login"))

    # 在收到 response 的时候，我们是不是应该做些什么...

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        # 现在之对于 request 进行处理
        path = request.path

        if path.endswith("/logout"):
            self.check_token_and_session(request)

        response = self.get_response(request)
        # Code to be executed for each request/response after
        # the view is called.
        if path.endswith("/login"):
            self.add_login_time(request)

        return response
