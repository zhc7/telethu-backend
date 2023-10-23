from channels.db import database_sync_to_async
from users.models import User
from datetime import datetime
from utils.session import WebSocketSessionData
from utils.utils_jwt import check_jwt_token
from django.http import JsonResponse
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

    # 除了利用 session 进行鉴权以外，还需要使用 request 当中的 JWT 进行鉴权
    @staticmethod
    async def check_token(scope):
        headers = scope["headers"]
        headers = {val.decode("utf-8"): key.decode("utf-8") for val, key in headers}
        jwt_token = headers["authorization"]
        check_result = check_jwt_token(jwt_token)
        print("check_result is ", check_result)
        session = WebSocketSessionData(scope)
        print("echo!")
        if check_result is not None:
            print("0")
            # 从 payload 当中获得 username 字段
            user_id = check_result["user_id"]
            print("00")
            users = User.objects.filter(id=user_id)
            print("000")
            if len(users) == 0:
                # 没有找到相应的 user
                return 0

        else:
            print("1")
            return 1

        if check_result["user_id"] != session.user_id:
            print("2")
            return 2

    # 完整的鉴权逻辑，在上面的注释当中有所提及
    async def check_token_and_session(self, scope):
        headers = scope["headers"]
        headers = {val.decode("utf-8"): key.decode("utf-8") for val, key in headers}
        token = headers.get("authorization")
        sessions = scope.get("session")
        print("session is: ", sessions.keys())
        ws_user_id = sessions.get("user_id")
        if token and ws_user_id:
            print("WS branch 1")
            token_result = self.check_token(scope)
            print("WS token result is: ", token_result)
            if token_result == 0:
                return JsonResponse({"code": 2, "info": "User not found"}, status=401)
            elif token_result == 1:
                return request_failed(
                    2, "JWT not found or JWT format error", status_code=401
                )
            elif token_result == 2:
                session = WebSocketSessionData(scope)
                if session.user_id is None:
                    return request_failed(
                        2, "WS Login has expired or haven't login 1!", status_code=401
                    )
                return request_failed(
                    2,
                    "User id in session and token doesn't match! ",
                    status_code=401,
                )
            login_result = self.check_last_login(scope)
            print("login_result is: ", login_result)
            if login_result is None:
                return request_failed(
                    2, "WS Login has expired or haven't login 2!", status_code=401
                )
        elif token and not ws_user_id:
            print("WS branch 2")
            check_result = check_jwt_token(token)
            session = WebSocketSessionData(scope)
            if check_result is None:
                return request_failed(2, "Invalid or expired JWT", status_code=401)
            else:
                session.user_id = check_result["user_id"]
        elif not token and ws_user_id:
            print("WS branch 3")
            session = WebSocketSessionData(scope)
            if session.user_id is None:
                return request_failed(
                    2, "WS Login has expired or haven't login 3!", status_code=401
                )
            login_result = self.check_last_login(scope)
            if login_result is None:
                return request_failed(
                    2, "WS Login has expired or haven't login 4!", status_code=401
                )
        else:
            print("WS branch 4")
            return request_failed(2, "Can't find session and token!", status_code=401)
        session = WebSocketSessionData(scope)
        return 0

    async def __call__(self, scope, receive, send):
        # Look up user from query string (you should also do things like
        # checking if it is a valid user ID, or if scope["user"] is already
        # populated).
        print("in WS middleware!")
        res = await self.check_token_and_session(scope)
        print("result is: ", res)
        if res != 0:
            return res
        print("session keys are: ", scope["session"].keys())
        new_scope = scope
        sessions = scope.get("session")
        my_user_id = sessions.get("user_id")
        print(scope.get("session"))
        new_scope["user_id"]= my_user_id
        print("out of WS middleware!")
        return await self.app(new_scope, receive, send)
