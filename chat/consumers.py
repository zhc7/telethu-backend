import json

import aio_pika
from channels.db import database_sync_to_async  # 引入异步数据库操作
from channels.generic.websocket import AsyncWebsocketConsumer

from users.models import Friendship, GroupList, User
from utils.data import (
    MessageType,
    TargetType,
    Message,
    ContactsData,
    UserData,
    GroupData,
    FriendType,
)
from utils.uid import globalIdMaker, globalMessageIdMaker


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = None
        self.rabbitmq_connection = None
        self.self_exchange = None
        self.friend_list: list[int] = []
        self.group_list: list[int] = []
        self.group_members = None
        self.group_names = None
        self.channel: aio_pika.Channel | None = None
        self.storage_exchange = None

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

    async def send_meta_info(self):
        group_info: dict[int, GroupData] = await self.query_group_info(self.group_list)
        friend_info: dict[int, UserData] = await self.query_friends_info(self.user_id)
        contacts_info: dict[int, ContactsData] = {}
        contacts_info.update(group_info)
        contacts_info.update(friend_info)
        contacts_info = {key: val.model_dump() for key, val in contacts_info.items()}
        await self.send(text_data=json.dumps(contacts_info))

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
        queue_name_receive = str(self.user_id)
        # 用户订阅好友的消息
        queue_receive = await self.channel.declare_queue(queue_name_receive)
        await queue_receive.bind(self.self_exchange)
        # 消费消息
        await queue_receive.consume(self.callback, no_ack=True)

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

    async def receive(self, text_data=None, _=None):
        # 接收来自前端的消息
        message_received = Message.model_validate_json(text_data)
        # 设置user_id
        message_received.sender = self.user_id
        # TODO: 分配 id
        message_received.message_id = globalMessageIdMaker.get_id()
        # TODO: 将 message_received basic_publish 到 connect 当中声明的 exchange 当中
        message_json = message_received.model_dump_json()
        await self.storage_exchange.publish(
            aio_pika.Message(
                body=message_json.encode(),  # 将消息转换为 bytes
            ),
            routing_key="",
        )
        print("send to storage: ", message_json)
        match message_received.m_type:
            case _ if message_received.m_type < MessageType.FUNCTION:
                if message_received.t_type == TargetType.FRIEND:
                    await self.send_message_friend(message_received)
                elif message_received.t_type == TargetType.GROUP:
                    await self.send_message_group(message_received)
            case MessageType.FUNC_CREATE_GROUP:
                await self.create_group(message_received)
            case MessageType.FUNC_ADD_GROUP_MEMBER:
                await self.add_group_member(message_received)
            case MessageType.FUNC_APPLY_FRIEND:
                await self.apply_friend(message_received)
            case MessageType.FUNC_ACCEPT_FRIEND:
                await self.accept_friend(message_received)
            case MessageType.FUNC_REJECT_FRIEND:
                await self.reject_friend(message_received)
    async def chat_message(self, message_sent: Message):
        await self.send(
            text_data=message_sent.model_dump_json()
        )  # send message to front no matter if it is user own message

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

    async def callback(self, body):
        message = Message.model_validate_json(body.body.decode())
        match message.m_type:
            case _ if message.m_type < MessageType.FUNCTION:
                await self.chat_message(message)
            case MessageType.FUNC_CREATE_GROUP:
                await self.get_create_massage(message)
            case MessageType.FUNC_ADD_GROUP_MEMBER:
                # 如果是刚刚被添加的人
                if str(message.receiver) == str(self.user_id):
                    await self.get_create_massage(message)
                else:
                    # 给群聊列表增加人
                    group_id = message.content
                    if group_id not in self.group_list:
                        print(
                            "group_id not in self.group_list,there is bug in callback"
                        )
                        print("group_id: ", group_id)
                        print("self.group_list: ", self.group_list)
                        print("self.user_id: ", self.user_id)
                    else:
                        self.group_members[group_id].append(message.receiver)
                        # 发送消息给前端
                        await self.chat_message(message)
            case MessageType.FUNC_APPLY_FRIEND:
                await self.chat_message(message)
            case MessageType.FUNC_ACCEPT_FRIEND:
                await self.chat_message(message)
            case MessageType.FUNC_REJECT_FRIEND:
                await self.chat_message(message)
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

    @database_sync_to_async
    def build_group(self, group_name, group_members):
        group = GroupList.objects.create(
            group_id=globalIdMaker.get_id(), group_name=group_name
        )
        group.group_members.set(group_members)
        group.save()
        return group

    async def create_group(self, message: Message):
        # 确保group_members是list[int],以后搬到鉴权里面
        if type(message.content.members) != list:
            return None
        if len(message.content.members) == 0 & type(message.content.members[0]) != int:
            return None
        # 建群
        if self.user_id not in message.content.members:
            message.content.members = [self.user_id] + message.content.members
        group_name = message.content.name
        group_members = message.content.members

        group = await self.build_group(group_name, group_members)
        message.content.id = group.group_id  # set receiver to group id
        # 通知每个成员
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
        group_id = message.content.id
        add_member = message.receiver
        group_member = await self.add_member(group_id, add_member)
        message.content.members.append(add_member)
        # 通知每个成员
        if group_member is None:
            return
        for member in group_member:
            await self.send_package_direct(message, str(member))

    async def send_message_group(self, message: Message):
        # 找到合适的exchange
        group_member = self.group_members[message.receiver]  # receiver is group id
        for member in group_member:
            await self.send_package_direct(message, str(member))

    async def get_create_massage(self, message: Message):
        # 更新自己的群聊列表
        group_id = message.content.id  # 这个是群聊的id
        if group_id not in self.group_list:
            self.group_list.append(group_id)
            self.group_members[group_id] = []
            self.group_names[group_id] = message.content.name
            self.group_members[group_id] = message.content.members
        else:
            for member in message.content.members:
                if member not in self.group_members[group_id]:
                    self.group_members[group_id].append(member)
            self.group_names[group_id] = message.content.name
            # 发送消息给前端
        await self.chat_message(message)

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
            await self.send_package_direct(message, str(friend_id)) # 发送消息给对方
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
        await self.send_package_direct(message, str(self.user_id))

    async def reject_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await self.friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_receive_apply:
            message.content = "Success"
            await self.send_package_direct(message, str(friend_id))
            await self.friendship_change(self.user_id, friend_id, 3)
        await self.send_package_direct(message, str(self.user_id))