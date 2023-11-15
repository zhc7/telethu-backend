import json
from typing import Callable, Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from channels.db import database_sync_to_async  # 引入异步数据库操作
from channels.generic.websocket import AsyncWebsocketConsumer

from files.models import Multimedia
from users.models import Friendship, GroupList, User
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
        # TODO: 建立一个全新的队列以及与它配套的 exchange，在 permanent_storage 当中进行接收
        # 和 相应的队列
        self.rabbitmq_connection = await aio_pika.connect_robust("amqp://localhost")
        self.channel = await self.rabbitmq_connection.channel()
        # 异步启动消息消费
        print("connected!")
        await self.start_consuming()
        await self.storage_start_consuming()
        # 发送好友列表
        await self.send_meta_info()

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
            MessageType.FUNC_CREATE_GROUP: self.create_group,
            MessageType.FUNC_ADD_GROUP_MEMBER: self.add_group_member,
            MessageType.FUNC_APPLY_FRIEND: self.apply_friend,
            MessageType.FUNC_ACCEPT_FRIEND: self.accept_friend,
            MessageType.FUNC_REJECT_FRIEND: self.reject_friend,
            MessageType.FUNC_BlOCK_FRIEND: self.block_friend,
            MessageType.FUNC_UNBLOCK_FRIEND: self.unblock_friend,
            MessageType.FUNC_DEL_FRIEND: self.delete_friend,
            MessageType.FUN_SEND_META: self.send_meta_info,
        }.get(message_received.m_type, self.handle_common_message)
        await handler(message_received)

    async def create_group(self, message: Message):
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
        group, user_list = await self.build_group(group_name, group_members)
        message.content.id = group.group_id  # set receiver to group id
        message.content.avatar = group.group_avatar
        message.content.members = await self.from_id_to_meta(user_list)
        for member in message.content.members:
            await self.send_package_direct(message, str(member.id))

    async def add_group_member(self, message: Message):
        # 确保group_members是list[int],以后搬到鉴权里面
        if not isinstance(message.content.members, list):
            return None
        if len(message.content.members) == 0 and not isinstance(
            message.content.members[0], int
        ):
            return None
        # 数据库加好友了，
        group_id = message.receiver
        group_members = message.content.members
        group, user_list = await self.add_member(group_id, group_members)
        if group is None:
            return None
        message.content.members = await self.from_id_to_meta(user_list)
        message.content.id = group.group_id
        message.content.name = group.group_name
        message.content.avatar = group.group_avatar
        for member in message.content.members:
            await self.send_package_direct(message, str(member.id))

    async def apply_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await self.friendship(self.user_id, friend_id)
        if (
            friendship_now == FriendType.relationship_not_exist
            or friendship_now == FriendType.already_been_reject
            or friendship_now == FriendType.already_reject_friend
        ):
            message.content = "Success"
            await self.send_package_direct(message, str(friend_id))  # 发送消息给对方
            await self.friendship_change(self.user_id, friend_id, 0)

        await self.send_package_direct(message, str(self.user_id))

    async def accept_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await self.friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_receive_apply:
            message.content = "Success"
            await self.send_package_direct(message, str(friend_id))
            await self.friendship_change(self.user_id, friend_id, 1)
        self.friend_list.append(friend_id)
        await self.send_package_direct(message, str(self.user_id))

    async def reject_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await self.friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_receive_apply:
            message.content = "Success reject"
            await self.send_package_direct(message, str(friend_id))
            await self.friendship_change(self.user_id, friend_id, 3)
        await self.send_package_direct(message, str(self.user_id))

    async def block_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await self.friendship(self.user_id, friend_id)
        if (
            friendship_now == FriendType.already_friend
            or friendship_now == FriendType.already_receive_apply
            or friendship_now == FriendType.already_send_apply
            or friendship_now == FriendType.already_reject_friend
            or friendship_now == FriendType.already_been_reject
        ):
            message.content = "Success"
            await self.send_package_direct(message, str(friend_id))
            await self.friendship_change(self.user_id, friend_id, 2)
        await self.send_package_direct(message, str(self.user_id))

    async def unblock_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await self.friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_block_friend:
            message.content = "Success"
            await self.send_package_direct(message, str(friend_id))
            await self.friendship_change(self.user_id, friend_id, 3)
        await self.send_package_direct(message, str(self.user_id))

    async def delete_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await self.friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_friend:
            message.content = "Success delete"
            await self.send_package_direct(message, str(friend_id))
            await self.friendship_change(self.user_id, friend_id, 3)
            self.friend_list.remove(friend_id)
        await self.send_package_direct(message, str(self.user_id))

    async def send_meta_info(self, _: Message = None):
        group_info: dict[int, GroupData] = await self.query_group_info(self.group_list)
        friend_info: dict[int, UserData] = await self.query_friends_info(self.user_id)
        contacts_info: dict[int, ContactsData] = {}
        contacts_info.update(group_info)
        contacts_info.update(friend_info)
        contacts_info = {key: val.model_dump() for key, val in contacts_info.items()}
        await self.send(text_data=json.dumps(contacts_info))

    async def handle_common_message(self, message_received: Message):
        if message_received.m_type != MessageType.TEXT:  # multimedia
            await self.handle_multimedia(message_received)
        if message_received.t_type == TargetType.FRIEND:
            await self.send_message_friend(message_received)
        elif message_received.t_type == TargetType.GROUP:
            await self.send_message_group(message_received)

    async def handle_multimedia(self, message: Message):
        m_type = message.m_type
        md5 = message.content
        t_type = message.t_type
        user_or_group = message.receiver
        await self.create_multimedia(m_type, md5, t_type, user_or_group)

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
        match message.m_type:
            case _ if message.m_type < MessageType.FUNCTION:
                await self.chat_message(message)
            case MessageType.FUNC_CREATE_GROUP:
                await self.get_create_massage(message)
                await self.ack_manager.acknowledge(message.message_id)
            case MessageType.FUNC_ADD_GROUP_MEMBER:
                await self.get_create_massage(message)
                await self.ack_manager.acknowledge(message.message_id)
            case MessageType.FUNC_APPLY_FRIEND:
                await self.chat_message(message)
            case MessageType.FUNC_ACCEPT_FRIEND:
                if str(message.receiver) == str(self.user_id):
                    self.friend_list.append(message.sender)
                await self.chat_message(message)
            case MessageType.FUNC_REJECT_FRIEND:
                await self.chat_message(message)
            case MessageType.FUNC_BlOCK_FRIEND:
                await self.chat_message(message)
            case MessageType.FUNC_UNBLOCK_FRIEND:
                await self.chat_message(message)
            case MessageType.FUNC_DEL_FRIEND:
                if str(message.receiver) == str(self.user_id):
                    self.friend_list.remove(message.sender)
                await self.chat_message(message)

    async def get_create_massage(self, message: Message):
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

    async def chat_message(self, message_sent: Message):
        await self.send(
            text_data=message_sent.model_dump_json()
        )  # send message to front no matter if it is user own message

    @database_sync_to_async
    def query_group_info(self, group_id_list) -> dict[int, GroupData]:
        # 这个方法执行同步数据库查询
        group_info = {}
        for group_id in group_id_list:
            group = GroupList.objects.filter(group_id=group_id).first()
            group_date = GroupData(
                id=group.group_id,
                name=group.group_name,
                avatar=group.group_avatar,
                members=[],
            )
            users_info = []
            for user in group.group_members.all():
                user_info = UserData(
                    id=user.id,
                    name=user.username,
                    avatar=user.avatar,
                    email=user.userEmail,
                )
                users_info.append(user_info)
            group_date.members = users_info
            group_info[group_id] = group_date
        return group_info

    @database_sync_to_async
    def query_friends_info(self, user_id) -> dict[int, UserData]:
        # 这个方法执行同步数据库查询
        friends_id = self._query_friends(user_id)
        friends_info = {}
        for friend_id in friends_id:
            friend = User.objects.filter(id=friend_id).first()
            friend_info = UserData(
                id=friend.id,
                name=friend.username,
                avatar=friend.avatar,
                email=friend.userEmail,
            )
            friends_info[friend_id] = friend_info
        return friends_info

    async def start_consuming(self):
        # 使用 Exchange 对象来声明交换机
        exchange_name = "user_" + str(self.user_id)  # name it after user_id
        self.self_exchange = await self.channel.declare_exchange(
            # use fanout exchange to broadcast to all user's queue
            exchange_name,
            type="fanout",
        )

        # 获取好友列表
        self.friend_list = await self.query_friends(self.user_id)
        # 获取群聊列表
        self.group_list, self.group_members, self.group_names = await self.query_group()

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

    @staticmethod
    def _query_friends(user_id):
        # 这个方法执行同步数据库查询
        friends = Friendship.objects.filter(user1=user_id)
        friends = friends | Friendship.objects.filter(user2=user_id)
        friends_id = []
        for friend in friends:
            if friend.state == 1:
                if str(friend.user1.id) == str(user_id):
                    friend_id = friend.user2.id
                else:
                    friend_id = friend.user1.id
                if friend_id not in friends_id:
                    friends_id.append(friend_id)
        return friends_id

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

    @database_sync_to_async
    def build_group(self, group_name, group_members):
        group = GroupList.objects.create(
            group_id=globalIdMaker.get_id(), group_name=group_name
        )
        for member in group_members:
            if member in self.friend_list or member == self.user_id:
                group.group_members.add(member)
        group.save()
        id_list = []
        for member in group.group_members.all():
            id_list.append(member.id)
        return group, id_list

    @database_sync_to_async
    def from_id_to_meta(self, id_list):
        users_info = []
        for user_id in id_list:
            user = User.objects.filter(id=user_id).first()
            user_info = UserData(
                id=user.id,
                name=user.username,
                avatar=user.avatar,
                email=user.userEmail,
            )
            users_info.append(user_info)
        return users_info

    @database_sync_to_async
    def friendship(self, user_id, friend_id):
        friendship = None
        # 排除自我添加
        if user_id == friend_id:
            return FriendType.user_equal_friend
        user = User.objects.filter(id=user_id).first()
        friend = User.objects.filter(id=friend_id).first()
        if friend is None:
            return FriendType.friend_not_exist, "friend_not_exist"
        # 检查是否已经是好友
        if user.user1_friendships.filter(user2=friend).exists():
            friendship = user.user1_friendships.get(user2=friend)
        elif user.user2_friendships.filter(user1=friend).exists():
            friendship = user.user2_friendships.get(user1=friend)
        if friendship is not None:
            if friendship.state == 1:
                return FriendType.already_friend, "already_friend"
            elif friendship.state == 0 and friendship.user1 == user:
                return FriendType.already_send_apply, "already_send_apply"
            elif friendship.state == 0 and friendship.user2 == user:
                return FriendType.already_receive_apply, "already_receive_apply"
            elif friendship.state == 2 and friendship.user1 == user:
                return FriendType.already_block_friend, "already_block_friend"
            elif friendship.state == 2 and friendship.user2 == user:
                return FriendType.already_been_block, "already_been_block"
            elif friendship.state == 3 and friendship.user1 == user:
                return FriendType.already_reject_friend, "already_reject_friend"
            elif friendship.state == 3 and friendship.user2 == user:
                return FriendType.already_been_reject, "already_been_reject"
        else:
            return FriendType.relationship_not_exist, "relationship_not_exist"

    @database_sync_to_async
    def add_member(self, group_id, add_member):
        group = GroupList.objects.filter(group_id=group_id).first()
        if group is None:
            print("group not exist")
            return None, None
        # 判断自己是否在群里，不在就加不了人
        user = User.objects.filter(id=self.user_id).first()
        if user not in group.group_members.all():
            print("user not in group")
            return None, None
        # 判断被加的是否是好友
        for member in add_member:
            if member in self.friend_list:
                group.group_members.add(member)
        group.save()
        id_list = []
        for member in group.group_members.all():
            id_list.append(member.id)
        return group, id_list

    @database_sync_to_async
    def friendship_change(self, user_id, friend_id, state):
        friendship = None
        # 排除自我添加
        if user_id == friend_id:
            return FriendType.user_equal_friend
        user = User.objects.filter(id=user_id).first()
        friend = User.objects.filter(id=friend_id).first()
        # 检查是否已经是好友
        if user.user1_friendships.filter(user2=friend).exists():
            friendship = user.user1_friendships.get(user2=friend)
        elif user.user2_friendships.filter(user1=friend).exists():
            friendship = user.user2_friendships.get(user1=friend)
        if friendship is not None:
            friendship.state = state
            friendship.user1 = user
            friendship.user2 = friend
            friendship.save()
            return True
        else:
            friendship = Friendship.objects.create(
                user1=user, user2=friend, state=state
            )
            friendship.save()
            return True

    @database_sync_to_async
    def create_multimedia(self, m_type, md5, t_type, user_or_group):
        if t_type == TargetType.FRIEND:  # IF FRIEND
            # if exist
            if Multimedia.objects.filter(multimedia_id=md5).exists():
                Multimedia.objects.filter(
                    multimedia_id=md5
                ).first().multimedia_user_listener.add(user_or_group)
                Multimedia.objects.filter(
                    multimedia_id=md5
                ).first().multimedia_user_listener.add(self.user_id)
            else:
                multimedia = Multimedia.objects.create(
                    multimedia_id=md5, multimedia_type=m_type
                )
                multimedia.multimedia_user_listener.add(user_or_group)
                multimedia.multimedia_user_listener.add(self.user_id)
                multimedia.save()
        elif t_type == TargetType.GROUP:  # IF GROUP
            # if exist
            if Multimedia.objects.filter(multimedia_id=md5).exists():
                Multimedia.objects.filter(
                    multimedia_id=md5
                ).first().multimedia_group_listener.add(user_or_group)
            else:
                multimedia = Multimedia.objects.create(
                    multimedia_id=md5, multimedia_type=m_type
                )
                multimedia.multimedia_group_listener.add(user_or_group)
                multimedia.save()
        return

    @database_sync_to_async
    def query_friends(self, user_id):
        return self._query_friends(user_id)

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
