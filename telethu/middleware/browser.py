from utils.session import WebSocketSessionData, SessionData
import uuid


class BrowserMiddleware:
    def __init__(self, app):
        # Store the ASGI application we were passed
        self.app = app

    @staticmethod
    def add_browser(scope):
        my_uid = uuid.uuid4()
        session = WebSocketSessionData(scope)
        session.browser = my_uid

    async def __call__(self, scope, receive, send):
        self.add_browser(scope)
        return await self.app(scope, receive, send)
