from utils.session import WebSocketSessionData, SessionData
import uuid


class BrowserMiddleware:
    def __init__(self, app):
        # Store the ASGI application we were passed
        self.app = app

    @staticmethod
    def add_browser(scope):
        session = WebSocketSessionData(scope)
        if not session.browser:
            session.browser = str(uuid.uuid4())

    async def __call__(self, scope, receive, send):
        print("In Browser Middleware")
        self.add_browser(scope)
        return await self.app(scope, receive, send)
