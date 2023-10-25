# chat/routing.py
from django.urls import re_path

from chat import consumers

websocket_urlpatterns = [
    re_path(r"ws/chat", consumers.ChatConsumer.as_asgi()),
]

# from channels.routing import ProtocolTypeRouter, URLRouter
# from django.urls import re_path
# from chat.consumers import ChatConsumer  # 导入你的 Consumer
# application = ProtocolTypeRouter({
#     "websocket": URLRouter([
#         re_path(r"ws/some_path/(?P<room_name>\w+)/$", YourConsumer.as_asgi()),
#         # 添加更多 WebSocket 路由
#     ]),
# })
