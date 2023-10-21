"""
ASGI config for telethu project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from channels.security.websocket import AllowedHostsOriginValidator
from chat.routing import websocket_urlpatterns
from channels.sessions import SessionMiddlewareStack
from chat import consumers
from django.urls import path  # Add this import
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
            AuthMiddlewareStack(
                SessionMiddlewareStack(
                    URLRouter(
                        websocket_urlpatterns + [
                            path("chat/", consumers.ChatConsumer.as_asgi()),
                        ]
                    )
                )
            )
        ),
    }
)
