# chat/consumers.py
import json
import pika
import aiormq
import aio_pika
import sys
from channels.generic.websocket import AsyncWebsocketConsumer
from users.models import User, Friendship
import asyncio
from channels.db import database_sync_to_async  # 引入异步数据库操作


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = None
        self.rabbitmq_connection = None
        self.exchange_send = None

    async def connect(self):
        # 建立 WebSocket 连接
        await self.accept()
        # 获取当前用户
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        # 异步启动消息消费
        await self.start_consuming()

    @database_sync_to_async
    def query_friends(self):
        # 这个方法执行同步数据库查询
        friends = Friendship.objects.filter(user1=self.user_id)
        friends = friends | Friendship.objects.filter(user2=self.user_id)
        friends_id = []
        for friend in friends:
            friend_id = friend.user1.id if friend.user1.id != self.user_id else friend.user2.id
            friends_id.append(friend_id)
        return friends_id

    async def start_consuming(self):
        # 建立rabbitmq连接
        self.rabbitmq_connection = await aio_pika.connect_robust("amqp://localhost")
        channel = await self.rabbitmq_connection.channel()
        # 使用 Exchange 对象来声明交换机
        exchange_name = str(self.user_id)
        exchange_send = await channel.declare_exchange(exchange_name, type='fanout')
        self.exchange_send = exchange_send
        # 获取好友列表
        friends_id = await self.query_friends()

        async def callback(body):
            message = body.body.decode()
            await self.chat_message(message)

        for friend_id in friends_id:
            # 建立queue
            queue_name_receive = str(friend_id) + "_" + str(self.user_id)
            queue_name_send = str(self.user_id) + "_" + str(friend_id)
            # 好友订阅用户的消息
            queue_send = await channel.declare_queue(queue_name_send)
            await queue_send.bind(exchange_send)
            # 用户订阅好友的消息
            exchange_name_receive = str(friend_id)
            exchange_receive = await channel.declare_exchange(exchange_name_receive, type='fanout')
            queue_receive = await channel.declare_queue(queue_name_receive)
            await queue_receive.bind(exchange_receive)
            # 消费消息
            await queue_receive.consume(callback)
        # 自己订阅自己的消息
        queue_name_send = str(self.user_id) + "_" + str(self.user_id)
        queue_send = await channel.declare_queue(queue_name_send)
        await queue_send.bind(exchange_send)
        await queue_send.consume(callback)

    async def disconnect(self, close_code):
        try:
            await self.rabbitmq_connection.close()
        except Exception as e:
            print(f"An error occurred while closing the RabbitMQ connection: {str(e)}")

    async def receive(self, text_data):
        # 接收来自前端的消息
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        # 发送消息给rabbitmq
        await self.exchange_send.publish(
            aio_pika.Message(
                body=message.encode(),  # 将消息转换为 bytes
            ),
            routing_key='',  # 不指定 routing_key
        )

    async def chat_message(self, message):
        # 处理来自rabbitmq队列的消息发送消息给前端
        await self.send(text_data=json.dumps({
            'message': message
        }))
