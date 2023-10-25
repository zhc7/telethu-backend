"""
ASGI config for telethu project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os
import threading

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from telethu.middleware.connect import QueryAuthMiddleware
from channels.security.websocket import AllowedHostsOriginValidator
from chat.routing import websocket_urlpatterns
from channels.sessions import SessionMiddlewareStack
from chat import consumers
from django.urls import path  # Add this import

from utils.storage import start_storage

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "telethu.settings")
# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

import chat.routing

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),  # add when create the chat app.I don't know if I need to delete the column below.
        # "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(QueryAuthMiddleware(URLRouter(websocket_urlpatterns))),
            # 这里的写法基于这样的事实：我们希望发送的 WebSocket 请求通过我们自己编写的 QueryAuthMiddleware；
            # 同时外面需要套上 AuthMiddlewareStack 才可以在 Scope 当中获取 session 字段
        ),
    }
)

threading.Thread(target=start_storage).start()
