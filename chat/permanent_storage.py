from consumers import Message
from channels.db import database_sync_to_async  # 引入异步数据库操作
from channels.generic.websocket import AsyncWebsocketConsumer
import aio_pika


class PermStore:
    def __init__(self, *args, **kwargs):
        self.rabbitmq_connection = None

    async def receive(self):
        self.rabbitmq_connection = await aio_pika.connect_robust("amqp://localhost")
        channel = await self.rabbitmq_connection.channel()
        await channel.declare_exchange("storage", type="direct")
        queue_receive = await channel.declare_queue("permanent_storage")
