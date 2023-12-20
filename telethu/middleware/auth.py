from datetime import datetime

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

    @staticmethod
    def check_token_and_session(request):
        token = request.headers.get("Authorization")
        print("token is: ", token)
        session = SessionData(request)
        user_id = check_jwt_token(token)
        print("jwt check result", user_id)
        if user_id is None:
            return request_failed(2, "Invalid Token", 401)
        session.user_id = user_id
        request.user_id = user_id
        return 0

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.
        # 现在之对于 request 进行处理
        path = request.path
        print("In auth middleware!")
        if (
            not path.endswith("/login")
            and not path.endswith("login_with_email")
            and not path.startswith("/users/email_exists")
            and not path.endswith("/register")
            and not path.endswith("/receive_code")
            and "verify" not in path
        ):
            print("You are not logging in!")
            result = self.check_token_and_session(request)
            session = SessionData(request)
            if path.endswith("/delete_user"):
                session.user_id = None
            if result != 0:
                return result

        response = self.get_response(request)
        # Code to be executed for each request/response after
        # the view is called.
        if path.endswith("/login") or path.endswith("/login_with_email"):
            print("You are now logging in! ")
            self.add_login_time(request)
        print("Out of auth middleware!")
        return response
