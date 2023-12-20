from datetime import datetime

from django.http import JsonResponse, QueryDict

from users.models import User
from utils.session import WebSocketSessionData
from utils.utils_jwt import check_jwt_token
from utils.utils_request import request_failed


class QueryAuthMiddleware:
    """
    Custom middleware (insecure) that takes user IDs from the query string.
    """

    def __init__(self, app):
        # Store the ASGI application we were passed
        self.app = app

    @staticmethod
    def add_login_time(scope):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session = WebSocketSessionData(scope)
        session.last_login = current_time
        print("last_login at: ", session.last_login)

    # 在发送请求的时候，通过当前时间和 session 当中已经加入的 “last_login” 字段进行比较，如果超过一天就重定向到 login
    @staticmethod
    def check_last_login(scope):
        current_time = datetime.now()
        session = WebSocketSessionData(scope)
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
            return None
        return 0

    # 完整的鉴权逻辑，在上面的注释当中有所提及
    @staticmethod
    def check_token_and_session(scope):
        query_string = scope["query_string"].decode("utf-8")
        query_params = QueryDict(query_string)
        token = query_params.get("token")
        session = WebSocketSessionData(scope)
        user_id = check_jwt_token(token)
        if user_id is None:
            return request_failed(2, "Token Invalid", 401)
        session.user_id = user_id


    async def __call__(self, scope, receive, send):
        # Look up user from query string (you should also do things like
        # checking if it is a valid user ID, or if scope["user"] is already
        # populated).
        print("in WS middleware!")
        res = self.check_token_and_session(scope)
        print("result is: ", res)
        if res != 0:
            return res
        print("session keys are: ", scope["session"].keys())
        new_scope = scope
        sessions = scope.get("session")
        my_user_id = sessions.get("user_id")
        print(scope.get("session"))
        new_scope["user_id"] = my_user_id
        print("out of WS middleware!")
        return await self.app(new_scope, receive, send)
