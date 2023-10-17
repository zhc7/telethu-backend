# chat/consumers.py
import json
import pika
import aiormq
import aio_pika
import sys
from channels.generic.websocket import AsyncWebsocketConsumer
from users.models import User, Friendship
import asyncio
from channels.db import database_sync_to_async # 引入异步数据库操作


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = None
        self.rabbitmq_connection = None

    async def connect(self):
        # 建立 WebSocket 连接
        print("connecting")
        await self.accept()
        print("connected")
        # 获取当前用户
        # self.user_id = self.scope['user_id']
        self.user_id = 4
        # 异步启动消息消费
        print("start consuming")
        await self.start_consuming()
        print("done")

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
        print("start consuming")
        # 建立rabbitmq连接
        self.rabbitmq_connection = await aio_pika.connect_robust("amqp://localhost")
        channel = await self.rabbitmq_connection.channel()

        # 使用 Exchange 对象来声明交换机
        exchange_name = str(self.user_id)
        exchange_send = await channel.declare_exchange(exchange_name, type='fanout')
        print("exchange declared")
        print("start get friends")
        # 获取好友列表
        friends_id = await self.query_friends()
        print("get friends done")
        async def callback(ch, method, properties, body):
            message = body.decode()
            await self.chat_message(message)

        for friend_id in friends_id:
            # 建立queue

            queue_name_receive = str(friend_id) +"_" + str(self.user_id)
            queue_name_send = str(self.user_id)  +"_"+ str(friend_id)
            print(queue_name_receive)
            print(queue_name_send)
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

        # 使用异步的方式启动消费


    async def disconnect(self, close_code):
        try:
            await self.rabbitmq_connection.close()
        except Exception as e:
            print(f"An error occurred while closing the RabbitMQ connection: {str(e)}")

    async def receive(self, text_data):
        print("receiving")
        # 接收来自前端的消息
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        print(message)
        # 发送消息给rabbitmq
        channel = self.rabbitmq_connection.channel()
        exchange_name = str(self.user_id)   # 交换机名称
        exchange_send = await channel.declare_exchange(exchange_name, type='fanout')
        channel.basic_publish(exchange_send, routing_key='', body=message)

    async def chat_message(self, message):
        # 处理来自rabbitmq队列的消息发送消息给前端
        await self.send(text_data=json.dumps({
            'message': message
        }))
