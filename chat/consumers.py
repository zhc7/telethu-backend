import json
from typing import Callable, Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
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
    db_reduce_person,
    db_change_group_owner,
    db_add_or_remove_admin,
    db_group_remove_member,
    db_set_top_message,
)

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
from utils.uid import globalMessageIdMaker


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
        self.group_members: dict[int, list[int]] = {}
        self.group_names = None
        self.group_owner: list[int] = []
        self.group_admin: dict[int, list[int]] = {}
        self.channel: aio_pika.Channel | None = None
        self.storage_exchange = None
        self.ack_manager = AckManager()
        self.received = {}

    async def connect(self):
        # websocket connect
        await self.accept()
        # get user id
        self.user_id = self.scope["user_id"]
        print("user id we get in connect is: ", self.user_id)
        # rabbitmq connect
        self.rabbitmq_connection = await aio_pika.connect_robust("amqp://localhost")
        self.channel = await self.rabbitmq_connection.channel()
        # start consuming
        print("connected!")
        await self.start_consuming()
        await self.storage_start_consuming()
        # send meta info to front
        await self.rcv_send_meta_info()

    async def start_consuming(self):
        exchange_name = "user_" + str(self.user_id)  # name it after user_id
        self.self_exchange = await self.channel.declare_exchange(
            # use fanout exchange to broadcast to all user's queue
            exchange_name,
            type="fanout",
        )
        # get friend list
        self.friend_list = await db_query_friends(self.user_id)
        # get group list
        (
            self.group_list,
            self.group_members,
            self.group_names,
            self.group_owner,
            self.group_admin,
        ) = await db_query_group(self.user_id)
        # build queue and bind to exchange to receive message from rabbitmq server
        queue_name_receive = self.scope["session"]["browser"]
        queue_receive = await self.channel.declare_queue(queue_name_receive)
        await queue_receive.bind(self.self_exchange)
        # start consuming
        await queue_receive.consume(self.callback)

    async def storage_start_consuming(self):
        # build storage exchange
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
        if message_received.m_type != MessageType.FUNC_READ_MESSAGE:
            message_json = message_received.model_dump_json()
            await self.storage_exchange.publish(
                aio_pika.Message(
                    body=message_json.encode(),  # turn message into bytes
                ),
                routing_key="",
            )
            print("send to storage: ", message_json)

        # step 4. handle message
        # to sync across same user's different devices
        Message.sender = self.user_id
        handler: Callable[[Message], Any] = {
            MessageType.FUNC_CREATE_GROUP: self.rcv_create_group,
            MessageType.FUNC_ADD_GROUP_MEMBER: self.rcv_add_group_member,
            MessageType.FUNC_APPLY_FRIEND: self.rcv_apply_friend,
            MessageType.FUNC_ACCEPT_FRIEND: self.rcv_accept_friend,
            MessageType.FUNC_REJECT_FRIEND: self.rcv_reject_friend,
            MessageType.FUNC_BlOCK_FRIEND: self.rcv_block_friend,
            MessageType.FUNC_UNBLOCK_FRIEND: self.rcv_unblock_friend,
            MessageType.FUNC_DEL_FRIEND: self.rcv_delete_friend,
            MessageType.FUNC_SEND_META: self.rcv_send_meta_info,
            MessageType.FUNC_READ_MESSAGE: self.rcv_read_message,
            MessageType.FUNC_LEAVE_GROUP: self.rcv_leave_group,
            MessageType.FUNC_CHANGE_GROUP_OWNER: self.rcv_change_group_owner,
            MessageType.FUNC_ADD_GROUP_ADMIN: self.rcv_add_or_reduce_admin,
            MessageType.FUNC_REMOVE_GROUP_ADMIN: self.rcv_add_or_reduce_admin,
            MessageType.FUNC_REMOVE_GROUP_MEMBER: self.rcv_remove_group_member,
            MessageType.FUNC_MESSAGE_BROADCAST: self.rcv_set_top_message,
        }.get(message_received.m_type, self.rcv_handle_common_message)
        await handler(message_received)

    async def rcv_create_group(self, message: Message):
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
            await self.send_message_to_target(message, str(member))

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
            await self.send_message_to_target(message, str(member))

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
            await self.send_message_to_target(message, str(friend_id))
            await db_friendship_change(self.user_id, friend_id, 0)
        await self.send_message_to_target(message, str(self.user_id))

    async def rcv_accept_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await db_friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_receive_apply:
            message.content = "Success"
            await self.send_message_to_target(message, str(friend_id))
            await db_friendship_change(self.user_id, friend_id, 1)
        self.friend_list.append(friend_id)
        await self.send_message_to_target(message, str(self.user_id))

    async def rcv_reject_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await db_friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_receive_apply:
            message.content = "Success reject"
            await self.send_message_to_target(message, str(friend_id))
            await db_friendship_change(self.user_id, friend_id, 3)
        await self.send_message_to_target(message, str(self.user_id))

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
            await self.send_message_to_target(message, str(friend_id))
            await db_friendship_change(self.user_id, friend_id, 2)
        await self.send_message_to_target(message, str(self.user_id))

    async def rcv_unblock_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await db_friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_block_friend:
            message.content = "Success"
            await self.send_message_to_target(message, str(friend_id))
            await db_friendship_change(self.user_id, friend_id, 3)
        await self.send_message_to_target(message, str(self.user_id))

    async def rcv_delete_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await db_friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_friend:
            message.content = "Success delete"
            await self.send_message_to_target(message, str(friend_id))
            await db_friendship_change(self.user_id, friend_id, 3)
            self.friend_list.remove(friend_id)
        await self.send_message_to_target(message, str(self.user_id))

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
            await self.send_message_to_target(message, str(self.user_id))
            await self.send_message_to_target(message, str(message_sender))
        else:
            message.content = message_sender
            await self.send_message_to_target(message, str(self.user_id))

    async def rcv_leave_group(self, message: Message):
        group_id = message.receiver
        user_id = self.user_id
        if group_id not in self.group_list:
            message.content = "You are not in this group"
            await self.send_message_to_target(message, str(user_id))
            return
        message.sender = user_id
        message.t_type = TargetType.GROUP
        message.content = "user:id=" + str(user_id) + " leave group"
        group_other_members = self.group_members[group_id]
        self.group_list.remove(group_id)
        self.group_members.pop(group_id)
        self.group_names.pop(group_id)
        await db_reduce_person(group_id, user_id)
        for member in group_other_members:
            await self.send_message_to_target(message, str(member))
        await self.send_message_to_target(message, str(user_id))

    async def rcv_change_group_owner(self, message: Message):
        group_old_owner = self.user_id
        group_new_owner = message.receiver
        group_id = message.content
        if group_old_owner == group_new_owner:
            message.content = "You are already the owner"
            await self.send_message_to_front(message)
            return
        if group_id not in self.group_list:
            message.content = "You are not in this group"
            await self.send_message_to_front(message)
            return
        if group_new_owner not in self.group_members[group_id]:
            message.content = "This user is not in this group"
            await self.send_message_to_front(message)
            return
        try:
            await db_change_group_owner(group_id, group_old_owner, group_new_owner)
        except KeyError as e:
            message.content = str(e)
            await self.send_message_to_front(message)
            return
        for member in self.group_members[group_id]:
            await self.send_message_to_target(message, str(member))

    async def rcv_add_or_reduce_admin(self, message: Message):
        group_id = message.content
        group_admin = message.receiver
        if message.m_type == MessageType.FUNC_REMOVE_GROUP_ADMIN:
            if_add = False
        else:
            if_add = True
        try:
            await db_add_or_remove_admin(group_id, group_admin, self.user_id, if_add)
        except KeyError as e:
            message.content = str(e)
            await self.send_message_to_front(message)
            return
        if if_add:
            self.group_admin[group_id].append(group_admin)
        else:
            self.group_admin[group_id].remove(group_admin)
        for member in self.group_members[group_id]:
            await self.send_message_to_target(message, str(member))

    async def rcv_remove_group_member(self, message: Message):
        group_id = message.content
        group_member = message.receiver
        try:
            await db_group_remove_member(group_id, group_member, self.user_id)
        except KeyError as e:
            message.content = str(e)
            await self.send_message_to_front(message)
            return
        self.group_members[group_id].remove(group_member)
        for member in self.group_members[group_id]:
            await self.send_message_to_target(message, str(member))
        await self.send_message_to_target(message, str(group_member))

    async def rcv_set_top_message(self, message: Message):
        group_id = message.receiver
        message_id = message.content
        try:
            await db_set_top_message(group_id, message_id, self.user_id)
        except KeyError as e:
            message.content = str(e)
            await self.send_message_to_front(message)
            return
        for member in self.group_members[group_id]:
            await self.send_message_to_target(message, str(member))

    async def rcv_handle_common_message(self, message_received: Message):
        if message_received.m_type != MessageType.TEXT:  # multimedia
            m_type = message_received.m_type
            md5 = message_received.content
            t_type = message_received.t_type
            user_or_group = message_received.receiver
            await db_create_multimedia(self.user_id, m_type, md5, t_type, user_or_group)
        if message_received.t_type == TargetType.FRIEND:  # send message to friend
            if message_received.receiver in self.friend_list:
                await self.send_message_to_target(
                    message_received, str(message_received.receiver)
                )
            await self.send_message_to_target(message_received, str(self.user_id))
        elif message_received.t_type == TargetType.GROUP:
            group_member = self.group_members[
                message_received.receiver
            ]  # receiver is group id
            for member in group_member:
                await self.send_message_to_target(message_received, str(member))
            await self.send_message_to_target(message_received, str(self.user_id))

    async def callback(self, body: AbstractIncomingMessage):
        message = Message.model_validate_json(body.body.decode())
        ack_callback = body.channel.basic_ack(delivery_tag=body.delivery_tag)

        async def push_message(retry=self.retry):
            if retry == 0:
                return
            await self.send_message_to_front(message)
            print("pushed", message.model_dump())
            await self.ack_manager.manage(
                message.message_id, ack_callback, push_message(retry - 1), self.timeout
            )

        await push_message()
        handler: Callable[[Message], Any] = {
            MessageType.FUNC_CREATE_GROUP: self.cb_group_create_or_add,
            MessageType.FUNC_ADD_GROUP_MEMBER: self.cb_group_create_or_add,
            MessageType.FUNC_APPLY_FRIEND: self.send_message_to_front,
            MessageType.FUNC_ACCEPT_FRIEND: self.cb_accept_friend,
            MessageType.FUNC_REJECT_FRIEND: self.send_message_to_front,
            MessageType.FUNC_BlOCK_FRIEND: self.send_message_to_front,
            MessageType.FUNC_UNBLOCK_FRIEND: self.send_message_to_front,
            MessageType.FUNC_DEL_FRIEND: self.cb_del_friend,
            MessageType.FUNC_READ_MESSAGE: self.send_message_to_front,
            MessageType.FUNC_LEAVE_GROUP: self.cb_group_reduce,
            MessageType.FUNC_CHANGE_GROUP_OWNER: self.cb_group_change_owner,
            MessageType.FUNC_ADD_GROUP_ADMIN: self.cb_add_or_remove_admin,
            MessageType.FUNC_REMOVE_GROUP_ADMIN: self.cb_add_or_remove_admin,
            MessageType.FUNC_REMOVE_GROUP_MEMBER: self.cb_group_remove_member,
            MessageType.FUNC_MESSAGE_BROADCAST: self.send_message_to_front(message),
        }.get(message.m_type, self.send_message_to_front)
        await handler(message)

    async def cb_del_friend(self, message):
        if str(message.receiver) == str(self.user_id):
            self.friend_list.remove(message.sender)
        await self.send_message_to_front(message)

    async def cb_accept_friend(self, message):
        if str(message.receiver) == str(self.user_id):
            self.friend_list.append(message.sender)
        await self.send_message_to_front(message)

    async def cb_group_create_or_add(self, message: Message):
        group_id = message.content.id  # this is group id
        if group_id not in self.group_list:
            self.group_list.append(group_id)
            self.group_members[group_id] = []
            self.group_names[group_id] = message.content.name
            for member in message.content.members:
                self.group_members[group_id].append(int(member))
        else:
            for member in message.content.members:
                if member not in self.group_members[group_id]:
                    self.group_members[group_id].append(int(member))
            self.group_names[group_id] = message.content.name
        await self.send_message_to_front(message)

    async def cb_group_reduce(self, message: Message):
        group_id = message.receiver
        user_reduce = message.sender
        if group_id in self.group_list:
            if user_reduce in self.group_members[group_id]:
                self.group_members[group_id].remove(int(user_reduce))
            if user_reduce == self.user_id:
                self.group_list.remove(group_id)
                self.group_members.pop(group_id)
                self.group_names.pop(group_id)
        await self.send_message_to_front(message)

    async def cb_group_change_owner(self, message: Message):
        self.group_owner[message.content] = message.receiver
        await self.send_message_to_front(message)

    async def cb_add_or_remove_admin(self, message: Message):
        if message.m_type == MessageType.FUNC_ADD_GROUP_ADMIN:
            if message.receiver not in self.group_admin[message.content]:
                self.group_admin[message.content].append(message.receiver)
        else:
            if message.receiver in self.group_admin[message.content]:
                self.group_admin[message.content].remove(message.receiver)
        await self.send_message_to_front(message)

    async def cb_group_remove_member(self, message: Message):
        group_id = message.content
        user_remove = message.receiver
        if self.user_id == user_remove and group_id in self.group_list:
            self.group_list.remove(group_id)
            self.group_members.pop(group_id)
            self.group_names.pop(group_id)
        else:
            if group_id in self.group_list:
                if user_remove in self.group_members[group_id]:
                    self.group_members[group_id].remove(int(user_remove))
                if user_remove in self.group_admin[group_id]:
                    self.group_admin[group_id].remove(int(user_remove))
        await self.send_message_to_front(message)

    async def send_message_to_front(self, message_sent: Message):
        await self.send(
            text_data=message_sent.model_dump_json()
        )  # send message to front no matter if it is user own message

    async def send_message_to_target(self, message: Message, receiver: str):
        message_json = message.model_dump_json()
        exchange_name = "user_" + receiver
        aim_exchange = await self.channel.declare_exchange(exchange_name, type="fanout")
        await aim_exchange.publish(
            aio_pika.Message(
                body=message_json.encode(),
            ),
            routing_key="",  # do not specify routing key
        )
