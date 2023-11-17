import json
from typing import Callable, Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from channels.db import database_sync_to_async  # 引入异步数据库操作
from channels.generic.websocket import AsyncWebsocketConsumer
from utils.db_fun import (
    db_query_group_info,
    db_query_friends,
    db_query_friends_info,
    db_build_group,
    db_from_id_to_meta,
    db_friendship,
    db_add_member,
    db_friendship_change,
    db_create_multimedia,
    db_query_group,
    db_add_read_message,
)

from files.models import Multimedia
from users.models import Friendship, GroupList, User, MessageList
from utils.ack_manager import AckManager
from utils.data import (
    MessageType,
    TargetType,
    Message,
    ContactsData,
    UserData,
    GroupData,
    FriendType,
    Ack,
)
from utils.uid import globalIdMaker, globalMessageIdMaker


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.retry = 5
        self.timeout = 1
        self.user_id = None
        self.rabbitmq_connection = None
        self.self_exchange = None
        self.friend_list: list[int] = []
        self.group_list: list[int] = []
        self.group_members = None
        self.group_names = None
        self.channel: aio_pika.Channel | None = None
        self.storage_exchange = None
        self.ack_manager = AckManager()
        self.received = {}

    async def connect(self):
        # 建立 WebSocket 连接
        await self.accept()
        # 获取当前用户
        self.user_id = self.scope["user_id"]
        print("user id we get in connect is: ", self.user_id)
        # 和 相应的队列
        self.rabbitmq_connection = await aio_pika.connect_robust("amqp://localhost")
        self.channel = await self.rabbitmq_connection.channel()
        # 异步启动消息消费
        print("connected!")
        await self.start_consuming()
        await self.storage_start_consuming()
        # 发送好友列表
        await self.rcv_send_meta_info()

    async def receive(self, text_data=None, _=None):
        # step 1. parse data
        dict_data = json.loads(text_data)
        print(dict_data)
        if "m_type" not in dict_data:
            # received an ack message
            ack_received = Ack.model_validate(dict_data)
            await self.ack_manager.acknowledge(ack_received.message_id)
            return
        # received a normal message
        message_received = Message.model_validate(dict_data)
        print(message_received.model_dump())
        message_received.sender = self.user_id

        # step 2. give back ack
        tmp_id = message_received.message_id
        print("received tmp_id", tmp_id)
        if tmp_id in self.received:
            await self.send(
                Ack(
                    message_id=self.received[tmp_id].message_id,
                    reference=tmp_id,
                ).model_dump_json()
            )
            return
        message_received.message_id = globalMessageIdMaker.get_id()
        self.received[tmp_id] = message_received
        await self.send(
            Ack(
                message_id=message_received.message_id,
                reference=tmp_id,
            ).model_dump_json()
        )

        # step 3. publish message to persistent storage queue
        if message_received.m_type != MessageType.READ_MESSAGE:
            message_json = message_received.model_dump_json()
            await self.storage_exchange.publish(
                aio_pika.Message(
                    body=message_json.encode(),  # 将消息转换为 bytes
                ),
                routing_key="",
            )
            print("send to storage: ", message_json)

        # step 4. handle message
        # to sync across same user's different devices
        handler: Callable[[Message], Any] = {
            MessageType.FUNC_CREATE_GROUP: self.rcv_create_group,
            MessageType.FUNC_ADD_GROUP_MEMBER: self.rcv_add_group_member,
            MessageType.FUNC_APPLY_FRIEND: self.rcv_apply_friend,
            MessageType.FUNC_ACCEPT_FRIEND: self.rcv_accept_friend,
            MessageType.FUNC_REJECT_FRIEND: self.rcv_reject_friend,
            MessageType.FUNC_BlOCK_FRIEND: self.rcv_block_friend,
            MessageType.FUNC_UNBLOCK_FRIEND: self.rcv_unblock_friend,
            MessageType.FUNC_DEL_FRIEND: self.rcv_delete_friend,
            MessageType.FUN_SEND_META: self.rcv_send_meta_info,
            MessageType.READ_MESSAGE: self.rcv_read_message,
        }.get(message_received.m_type, self.rcv_handle_common_message)
        await handler(message_received)

    async def rcv_create_group(self, message: Message):
        # 确保group_members是list[int],以后搬到鉴权里面
        if not isinstance(message.content.members, list):
            return None
        if len(message.content.members) == 0 and not isinstance(
            message.content.members[0], int
        ):
            return None
        # 建群
        if self.user_id not in message.content.members:
            message.content.members = [self.user_id] + message.content.members
        group_name = message.content.name
        group_members = message.content.members
        group, user_list = await db_build_group(
            self.friend_list, self.user_id, group_name, group_members
        )
        message.content.id = group.group_id  # set receiver to group id
        message.content.avatar = group.group_avatar
        message.content.members = await db_from_id_to_meta(user_list)
        for member in message.content.members:
            await self.send_package_direct(message, str(member.id))

    async def rcv_add_group_member(self, message: Message):
        if not isinstance(message.content.members, list):
            return None
        if len(message.content.members) == 0 and not isinstance(
            message.content.members[0], int
        ):
            return None
        group_id = message.receiver
        group_members = message.content.members
        group, user_list = await db_add_member(
            self.user_id, self.friend_list, group_id, group_members
        )
        if group is None:
            return None
        message.content.members = await db_from_id_to_meta(user_list)
        message.content.id = group.group_id
        message.content.name = group.group_name
        message.content.avatar = group.group_avatar
        for member in message.content.members:
            await self.send_package_direct(message, str(member.id))

    async def rcv_apply_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await db_friendship(self.user_id, friend_id)
        if (
            friendship_now == FriendType.relationship_not_exist
            or friendship_now == FriendType.already_been_reject
            or friendship_now == FriendType.already_reject_friend
        ):
            message.content = "Success"
            await self.send_package_direct(message, str(friend_id))
            await db_friendship_change(self.user_id, friend_id, 0)
        await self.send_package_direct(message, str(self.user_id))

    async def rcv_accept_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await db_friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_receive_apply:
            message.content = "Success"
            await self.send_package_direct(message, str(friend_id))
            await db_friendship_change(self.user_id, friend_id, 1)
        self.friend_list.append(friend_id)
        await self.send_package_direct(message, str(self.user_id))

    async def rcv_reject_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await db_friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_receive_apply:
            message.content = "Success reject"
            await self.send_package_direct(message, str(friend_id))
            await db_friendship_change(self.user_id, friend_id, 3)
        await self.send_package_direct(message, str(self.user_id))

    async def rcv_block_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await db_friendship(self.user_id, friend_id)
        if (
            friendship_now == FriendType.already_friend
            or friendship_now == FriendType.already_receive_apply
            or friendship_now == FriendType.already_send_apply
            or friendship_now == FriendType.already_reject_friend
            or friendship_now == FriendType.already_been_reject
        ):
            message.content = "Success"
            await self.send_package_direct(message, str(friend_id))
            await db_friendship_change(self.user_id, friend_id, 2)
        await self.send_package_direct(message, str(self.user_id))

    async def rcv_unblock_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await db_friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_block_friend:
            message.content = "Success"
            await self.send_package_direct(message, str(friend_id))
            await db_friendship_change(self.user_id, friend_id, 3)
        await self.send_package_direct(message, str(self.user_id))

    async def rcv_delete_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await db_friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_friend:
            message.content = "Success delete"
            await self.send_package_direct(message, str(friend_id))
            await db_friendship_change(self.user_id, friend_id, 3)
            self.friend_list.remove(friend_id)
        await self.send_package_direct(message, str(self.user_id))

    async def rcv_send_meta_info(self, _: Message = None):
        group_info: dict[int, GroupData] = await db_query_group_info(self.group_list)
        friends_id = await db_query_friends(self.user_id)
        friend_info: dict[int, UserData] = await db_query_friends_info(friends_id)
        contacts_info: dict[int, ContactsData] = {}
        contacts_info.update(group_info)
        contacts_info.update(friend_info)
        contacts_info = {key: val.model_dump() for key, val in contacts_info.items()}
        await self.send(text_data=json.dumps(contacts_info))

    async def rcv_read_message(self, message: Message):
        message_id = int(message.content)
        message_sender, message_receiver, message_t_type = await db_add_read_message(
            self.group_list, message_id, self.user_id
        )
        if type(message_sender) == int:
            message.receiver = message_receiver
            message.t_type = message_t_type
            message.sender = self.user_id
            await self.send_package_direct(message, str(self.user_id))
            await self.send_package_direct(message, str(message_sender))
        else:
            message.content = message_sender
            await self.send_package_direct(message, str(self.user_id))

    async def rcv_handle_common_message(self, message_received: Message):
        if message_received.m_type != MessageType.TEXT:  # multimedia
            m_type = message_received.m_type
            md5 = message_received.content
            t_type = message_received.t_type
            user_or_group = message_received.receiver
            await db_create_multimedia(self.user_id, m_type, md5, t_type, user_or_group)
        if message_received.t_type == TargetType.FRIEND:
            await self.send_message_friend(message_received)
        elif message_received.t_type == TargetType.GROUP:
            await self.send_message_group(message_received)

    async def callback(self, body: AbstractIncomingMessage):
        message = Message.model_validate_json(body.body.decode())
        ack_callback = body.channel.basic_ack(delivery_tag=body.delivery_tag)

        async def push_message(retry=self.retry):
            if retry == 0:
                return
            await self.chat_message(message)
            print("pushed", message.model_dump())
            await self.ack_manager.manage(
                message.message_id, ack_callback, push_message(retry - 1), self.timeout
            )

        await push_message()
        handler: Callable[[Message], Any] = {
            MessageType.FUNC_CREATE_GROUP: self.cb_group_create_or_add,
            MessageType.FUNC_ADD_GROUP_MEMBER: self.cb_group_create_or_add,
            MessageType.FUNC_APPLY_FRIEND: self.chat_message,
            MessageType.FUNC_ACCEPT_FRIEND: self.cb_accept_friend,
            MessageType.FUNC_REJECT_FRIEND: self.chat_message,
            MessageType.FUNC_BlOCK_FRIEND: self.chat_message,
            MessageType.FUNC_UNBLOCK_FRIEND: self.chat_message,
            MessageType.FUNC_DEL_FRIEND: self.cb_del_friend,
            MessageType.FUNC_READ_MSG: self.chat_message,
        }.get(message.m_type, self.chat_message)
        await handler(message)

    async def cb_del_friend(self, message):
        if str(message.receiver) == str(self.user_id):
            self.friend_list.remove(message.sender)
        await self.chat_message(message)

    async def cb_accept_friend(self, message):
        if str(message.receiver) == str(self.user_id):
            self.friend_list.append(message.sender)
        await self.chat_message(message)

    async def cb_group_create_or_add(self, message: Message):
        # 更新自己的群聊列表
        group_id = message.content.id  # 这个是群聊的id
        if group_id not in self.group_list:
            self.group_list.append(group_id)
            self.group_members[group_id] = []
            self.group_names[group_id] = message.content.name
            for member in message.content.members:
                self.group_members[group_id].append(member.id)
        else:
            for member in message.content.members:
                if member.id not in self.group_members[group_id]:
                    self.group_members[group_id].append(member.id)
            self.group_names[group_id] = message.content.name
            # 发送消息给前端
        await self.chat_message(message)
        await self.ack_manager.acknowledge(message.message_id)

    async def chat_message(self, message_sent: Message):
        await self.send(
            text_data=message_sent.model_dump_json()
        )  # send message to front no matter if it is user own message

    async def start_consuming(self):
        # 使用 Exchange 对象来声明交换机
        exchange_name = "user_" + str(self.user_id)  # name it after user_id
        self.self_exchange = await self.channel.declare_exchange(
            # use fanout exchange to broadcast to all user's queue
            exchange_name,
            type="fanout",
        )

        # 获取好友列表
        self.friend_list = await db_query_friends(self.user_id)
        # 获取群聊列表
        self.group_list, self.group_members, self.group_names = await db_query_group(
            self.user_id
        )

        # 建立queue
        queue_name_receive = self.scope["session"]["browser"]
        # 用户订阅好友的消息
        queue_receive = await self.channel.declare_queue(queue_name_receive)
        await queue_receive.bind(self.self_exchange)
        # 消费消息
        await queue_receive.consume(self.callback)

    async def storage_start_consuming(self):
        # 建立 exchange
        self.storage_exchange = await self.channel.declare_exchange(
            "storage", type="fanout"
        )
        storage_queue = await self.channel.declare_queue("PermStore")

        await storage_queue.bind(self.storage_exchange)

    async def disconnect(self, close_code):
        try:
            await self.rabbitmq_connection.close()
        except Exception as e:
            print(f"An error occurred while closing the RabbitMQ connection: {str(e)}")

    async def send_package_direct(
        self, message: Message, receiver: str
    ):  # 无论是什么，总会将一个package发送进direct queue
        message_json = message.model_dump_json()
        # 发送消息给rabbitmq
        exchange_name = "user_" + receiver
        aim_exchange = await self.channel.declare_exchange(exchange_name, type="fanout")
        await aim_exchange.publish(
            aio_pika.Message(
                body=message_json.encode(),  # 将消息转换为 bytes
            ),
            routing_key="",  # do not specify routing key
        )

    async def send_message_friend(self, message: Message):
        # 如果是自己的好友，直接发送消息
        if message.receiver in self.friend_list:
            await self.send_package_direct(message, str(message.receiver))
        await self.send_package_direct(message, str(self.user_id))

    async def send_message_group(self, message: Message):
        group_member = self.group_members[message.receiver]  # receiver is group id
        for member in group_member:
            await self.send_package_direct(message, str(member))
        await self.send_package_direct(message, str(self.user_id))
