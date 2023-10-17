# chat/consumers.py
import json
import pika
import sys
from channels.generic.websocket import AsyncWebsocketConsumer
from users.models import User, Friendship


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = None

    async def connect(self):
        # 建立 WebSocket 连接
        await self.accept()
        # 获取当前用户
        self.user_id = self.scope['user_id']
        # 异步启动消息消费
        await self.start_consuming()

    async def start_consuming(self):
        # 建立rabbitmq
        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
        channel = connection.channel()
        channel.exchange_declare(exchange=str(self.user_id), exchange_type='fanout')
        # 为所有好友建立联通的queue
        friends = Friendship.objects.filter(user1=self.user_id)
        friends = friends | Friendship.objects.filter(user2=self.user_id)

        def callback(ch, method, properties, body):
            massage = body.decode()
            self.chat_message(massage)

        for friend in friends:
            # 建立queue
            friend_id = friend.user1.id if friend.user1.id != self.user_id else friend.user2.id
            queue_name_receive = str(friend_id) + "|" + str(self.user_id)  # 放queue名称前面的是上传者，后面的是消费者
            queue_name_send = str(self.user_id) + "|" + str(friend_id)  # 放queue名称前面的是上传者，后面的是消费者
            # 建立好友订阅本人消息
            channel.queue_declare(queue=queue_name_send)
            channel.queue_bind(exchange=str(self.user_id), queue=queue_name_send)
            # 建立本人订阅好友消息
            channel.exchange_declare(exchange=str(friend_id), exchange_type='fanout')
            channel.queue_declare(queue=queue_name_receive)
            channel.queue_bind(exchange=str(friend_id), queue=queue_name_receive)
            # 开始消费
            channel.basic_consume(queue=queue_name_receive, on_message_callback=callback, auto_ack=True)

        await channel.start_consuming()

    async def disconnect(self, close_code):
        # 断开 WebSocket 连接
        pass

    async def receive(self, text_data):
        # 接收来自前端的消息
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        # 发送消息给rabbitmq
        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
        channel = connection.channel()
        channel.exchange_declare(exchange=str(self.user_id), exchange_type='fanout')
        channel.basic_publish(exchange=str(self.user_id), routing_key='', body=message)
        connection.close()

    async def chat_message(self, message):
        # 处理来自rabbitmq队列的消息发送消息给前端
        await self.send(text_data=json.dumps({
            'message': message
        }))
