# chat/consumers.py
import aio_pika
from channels.db import database_sync_to_async  # 引入异步数据库操作
from channels.generic.websocket import AsyncWebsocketConsumer
from pydantic import BaseModel

from users.models import Friendship


class MessageReceived(BaseModel):
    time: float
    m_type: str
    content: str
    receiver: int
    type: str = "message.received"


class MessageSent(BaseModel):
    time: float
    m_type: str
    content: str
    sender: int
    receiver: int


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = None
        self.rabbitmq_connection = None
        self.public_exchange = None

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
        exchange_name = "public_exchange"
        self.public_exchange = await channel.declare_exchange(exchange_name, type="direct")

        # 获取好友列表
        # friends_id = await self.query_friends()

        async def callback(body):
            message_sent = MessageSent.model_validate_json(body.body.decode())
            await self.chat_message(message_sent)

        # 建立queue
        queue_name_receive = str(self.user_id)
        # 用户订阅好友的消息
        queue_receive = await channel.declare_queue(queue_name_receive)
        await queue_receive.bind(self.public_exchange)
        # 消费消息
        await queue_receive.consume(callback)

    async def disconnect(self, close_code):
        try:
            await self.rabbitmq_connection.close()
        except Exception as e:
            print(f"An error occurred while closing the RabbitMQ connection: {str(e)}")

    async def receive(self, text_data=None, _=None):
        # 接收来自前端的消息
        message_received = MessageReceived.model_validate_json(text_data)
        message_sent = MessageSent(
            time=message_received.time,
            m_type=message_received.m_type,
            content=message_received.content,
            sender=self.user_id,
            receiver=message_received.receiver,
        )
        message_json = message_sent.model_dump_json()
        # 发送消息给rabbitmq
        await self.public_exchange.publish(
            aio_pika.Message(
                body=message_json.encode(),  # 将消息转换为 bytes
            ),
            routing_key=str(message_received.receiver),  # 不指定 routing_key
        )

    async def chat_message(self, message_sent: MessageSent):
        # 处理来自rabbitmq队列的消息发送消息给前端
        await self.send(text_data=message_sent.model_dump_json())
