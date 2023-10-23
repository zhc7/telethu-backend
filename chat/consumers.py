import enum
import json

import aio_pika
from channels.db import database_sync_to_async  # 引入异步数据库操作
from channels.generic.websocket import AsyncWebsocketConsumer
from pydantic import BaseModel

from users.models import Friendship, GroupList, User


class MessageType(enum.IntEnum):
    TEXT = 0
    IMAGE = 1
    AUDIO = 2
    VIDEO = 3
    FILE = 4
    FUNCTION = 5  # this marks the line between message and function, do not set this directly
    FUNC_ADD_FRIEND = 6
    FUNC_CREATE_GROUP = 7
    FUNC_ADD_GROUP_MEMBER = 8


class TargetType(enum.IntEnum):
    FRIEND = 0
    GROUP = 1
    OTHER = 2


class Message(BaseModel):
    m_type: MessageType = MessageType.TEXT
    t_type: TargetType = TargetType.OTHER
    time: float
    content: str | list | int  # 如果是消息，content 是 str，如果是函数，content 是 list,如果是群加人，这个放群id
    sender: int  # 如果是消息，sender 是发送者的 id，如果是函数，sender 是函数的发起者的 id。如果是群加人，这个放拉人的人
    receiver: int  # 如果是消息，receiver 是接收者的 id，如果是函数，receiver 是函数的接收者的 id。如果是群加人，这个放被拉的人
    info: str  # for message referencing, forwarding and appending info


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = None
        self.rabbitmq_connection = None
        self.public_exchange = None
        self.friend_list = None
        self.group_list = None
        self.group_members = None
        self.group_names = None

    async def connect(self):
        # 建立 WebSocket 连接
        await self.accept()
        # 获取当前用户
        self.user_id = self.scope["url_route"]["kwargs"]["user_id"]
        # 异步启动消息消费
        await self.start_consuming()
        # 发送好友列表
        await self.send_meta_info()

    @database_sync_to_async
    def query_group_info(self, group_id_list):
        # 这个方法执行同步数据库查询
        group_info = {}
        for group_id in group_id_list:
            group = GroupList.objects.filter(group_id=group_id).first()
            users_info = []
            for user in group.group_members.all():
                user_info = {
                    "user_id": user.id,
                    "username": user.username,
                    "avatar": user.avatar,
                }
                users_info.append(user_info)
            group_info[group_id] = users_info
        return group_info

    @database_sync_to_async
    def query_friends(self):
        # 这个方法执行同步数据库查询
        friends = Friendship.objects.filter(user1=self.user_id)
        friends = friends | Friendship.objects.filter(user2=self.user_id)
        friends_id = []
        for friend in friends:
            friend_id = (
                friend.user1.id if friend.user1.id != self.user_id else friend.user2.id
            )
            friends_id.append(friend_id)
        return friends_id

    async def send_meta_info(self):
        group_info = await self.query_group_info(self.group_list)
        group_info_json = json.dumps(group_info)
        await self.send(text_data=group_info_json)

    async def start_consuming(self):
        # 建立rabbitmq连接
        self.rabbitmq_connection = await aio_pika.connect_robust("amqp://localhost")
        channel = await self.rabbitmq_connection.channel()

        # 使用 Exchange 对象来声明交换机
        exchange_name = "public_exchange"
        self.public_exchange = await channel.declare_exchange(
            exchange_name, type="direct"
        )

        # 获取好友列表
        self.friend_list = await self.query_friends()
        # 获取群聊列表
        self.group_list, self.group_members, self.group_names = await self.query_group()

        # 建立queue
        queue_name_receive = str(self.user_id)
        # 用户订阅好友的消息
        queue_receive = await channel.declare_queue(queue_name_receive)
        await queue_receive.bind(self.public_exchange)
        # 消费消息
        await queue_receive.consume(self.callback, no_ack=True)

        # 用户订阅群聊的消息
        queue_for_group = await channel.declare_queue("group_" + str(self.user_id))
        for group_id in self.group_list:
            exchange = await channel.declare_exchange("group_" + str(group_id), type="fanout")
            await queue_for_group.bind(exchange, routing_key=str(group_id))
        await queue_for_group.consume(self.callback, no_ack=True)

    async def disconnect(self, close_code):
        try:
            await self.rabbitmq_connection.close()
        except Exception as e:
            print(f"An error occurred while closing the RabbitMQ connection: {str(e)}")

    async def receive(self, text_data=None, _=None):
        # 接收来自前端的消息
        message_received = Message.model_validate_json(text_data)
        match message_received.m_type:
            case _ if message_received.m_type < MessageType.FUNCTION:
                if message_received.t_type == TargetType.FRIEND:
                    await self.send_message_friend(message_received)
                elif message_received.t_type == TargetType.GROUP:
                    await self.send_message_group(message_received)
            case MessageType.FUNC_ADD_FRIEND:
                await self.create_group(message_received)
            case MessageType.FUNC_ADD_GROUP_MEMBER:
                await self.add_group_member(message_received)

    async def chat_message(self, message_sent: Message):
        # 处理来自rabbitmq队列的消息发送消息给前端
        await self.send(text_data=message_sent.model_dump_json())

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

    @database_sync_to_async
    def query_group(self):
        # 这个方法执行同步数据库查询
        groups = GroupList.objects.filter(group_members=self.user_id)
        group_id = []
        group_names = {}
        group_members = {}
        for group in groups:
            group_id.append(group.group_id)
            group_members_user = group.group_members.all()
            group_members_id = []
            for user in group_members_user:
                group_members_id.append(user.id)
            group_members[group.group_id] = group_members_id
            group_names[group.group_id] = group.group_name
        return group_id, group_members, group_names

    async def callback(self, body):
        message = Message.model_validate_json(body.body.decode())
        match message.m_type:
            case _ if message.m_type < MessageType.FUNCTION:
                await self.chat_message(message)
            case MessageType.FUNC_CREATE_GROUP:
                await self.get_create_massage(message)
            case MessageType.FUNC_ADD_GROUP_MEMBER:
                # 如果是刚刚被添加的人
                if message.receiver == self.user_id:
                    await self.get_create_massage(message)
                else:
                    # 给群聊列表增加人
                    group_id = message.receiver
                    if group_id not in self.group_list:
                        print("group_id not in self.group_list,there is bug in callback")
                    else:
                        self.group_members[group_id].append(message.receiver)
                        # 发送消息给前端
                        await self.chat_message(message)

    async def send_package_direct(self, message: Message, receiver: str):  # 无论是什么，总会将一个package发送进direct queue
        message_json = message.model_dump_json()
        # 发送消息给rabbitmq
        await self.public_exchange.publish(
            aio_pika.Message(
                body=message_json.encode(),  # 将消息转换为 bytes
            ),
            routing_key=receiver,  # 不指定 routing_key
        )

    async def send_message_friend(self, message: Message):
        # 如果是自己的好友，直接发送消息
        if message.receiver in self.friend_list:
            await self.send_package_direct(message, str(message.receiver))

    @database_sync_to_async
    def build_group(self, group_name, group_members):
        group = GroupList.objects.create(group_name=group_name)
        group.group_members.set(group_members)
        group.save()
        return group

    async def create_group(self, message: Message):
        # 建群
        group_name = message.info
        group_members = message.content
        group = await self.build_group(group_name, group_members)
        # 建立群聊专用交换机
        exchange_name = "group_" + str(group.group_id)
        channel = await self.rabbitmq_connection.channel()
        await channel.declare_exchange(exchange_name, type="fanout")
        # 通知每个成员
        message.sender = group.group_id
        for member in group_members:
            await self.send_package_direct(message, str(member))

    @database_sync_to_async
    def add_member(self, group_id, add_member):
        group = GroupList.objects.filter(group_id=group_id).first()
        # 判断自己是否在群里，不在就加不了人
        user = User.objects.filter(id=self.user_id).first()
        if user not in group.group_members.all():
            return None
        group.group_members.add(add_member)
        group.save()
        group_member = group.group_members.all()
        group_member_id = []
        for member in group_member:
            group_member_id.append(member.id)
        return group_member_id

    async def add_group_member(self, message: Message):
        # 数据库加好友了，
        group_id = message.content
        add_member = message.receiver
        group_member = await self.add_member(group_id, add_member)
        # 通知每个成员
        if group_member is None:
            return
        for member in group_member:
            await self.send_package_direct(message, str(member))

    async def send_message_group(self, message: Message):
        # 如果是自己的群，直接发送消息
        message_json = message.model_dump_json()
        # 找到合适的exchange
        exchange_name = "group_" + str(message.receiver)
        channel = await self.rabbitmq_connection.channel()
        exchange = await channel.declare_exchange(exchange_name, type="fanout")
        await exchange.publish(
            aio_pika.Message(
                body=message_json.encode(),  # 将消息转换为 bytes
            ),
            routing_key='',  # 不指定 routing_key
        )

    async def get_create_massage(self, message: Message):
        exchange_name = "group_" + str(message.sender)
        channel = await self.rabbitmq_connection.channel()
        exchange = await channel.declare_exchange(exchange_name, type="fanout")
        queue_name_receive = "group_" + str(self.user_id)
        queue_receive = await channel.declare_queue(queue_name_receive)
        await queue_receive.bind(exchange)
        await queue_receive.consume(self.callback, no_ack=True)
        # 更新自己的群聊列表
        group_id = message.sender  # 这个是群聊的id
        if group_id not in self.group_list:
            self.group_list.append(group_id)
            self.group_members[group_id] = []
            self.group_names[group_id] = message.info
            self.group_members[group_id] = message.content
        else:
            self.group_members[group_id].append(message.content)
            self.group_names[group_id] = message.info
            # 发送消息给前端
        await self.chat_message(message)
