import json
import time
from typing import Callable, Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from channels.generic.websocket import AsyncWebsocketConsumer

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
from utils.db_fun import (
    db_query_group_info,
    db_query_friends,
    db_query_friends_info,
    db_build_group,
    db_friendship,
    db_add_member,
    db_reject_candidate,
    db_friendship_change,
    db_create_multimedia,
    db_query_group,
    db_add_read_message,
    db_reduce_person,
    db_change_group_owner,
    db_add_or_remove_admin,
    db_group_remove_member,
    db_add_or_del_top_message,
    db_query_fri_and_gro_id,
    db_recall_member_message,
    db_delete_message,
    db_edit_message,
    db_recall_message,
    db_edit_profile,
    db_delete_group,
    db_change_group_name,
    db_reply,
    db_check_friend_if_deleted,
    db_check_friend_if_blocked,
)
from utils.uid import globalMessageIdMaker


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.retry = 5
        self.timeout = 5
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
        # await self.rcv_send_meta_info()
        await self.rcv_send_init_id()

    async def pseudo_connect(self, user_id: int):
        # websocket connect
        # get user id
        self.user_id = user_id
        print("user id we get in connect is: ", self.user_id)
        # rabbitmq connect
        self.rabbitmq_connection = await aio_pika.connect_robust("amqp://localhost")
        self.channel = await self.rabbitmq_connection.channel()
        # start consuming
        print("connected!")
        await self.pseudo_start_consuming(user_id)

    async def pseudo_start_consuming(self, user_id: int):
        exchange_name = "user_" + str(self.user_id)  # name it after user_id
        self.self_exchange = await self.channel.declare_exchange(
            # use fanout exchange to broadcast to all user's queue
            exchange_name,
            type="fanout",
        )
        # get friend list
        self.friend_list = await db_query_friends(self.user_id)
        # get group list
        await self.fresh_group_info()
        # build queue and bind to exchange to receive message from rabbitmq server
        queue_name_receive = str(user_id)
        queue_receive = await self.channel.declare_queue(queue_name_receive)
        await queue_receive.bind(self.self_exchange)
        # start consuming
        await queue_receive.consume(self.callback)

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
        await self.fresh_group_info()
        # build queue and bind to exchange to receive message from rabbitmq server
        queue_name_receive = self.scope["session"]["browser"]
        queue_receive = await self.channel.declare_queue(queue_name_receive)
        await queue_receive.bind(self.self_exchange)
        # start consuming
        await queue_receive.consume(self.callback)

    async def fresh_group_info(self):
        (
            self.group_list,
            self.group_members,
            self.group_names,
            self.group_owner,
            self.group_admin,
        ) = await db_query_group(self.user_id)

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
        # override fields
        message_received.sender = self.user_id
        message_received.who_read = []
        message_received.time = round(time.time() * 1000)
        message_received.t_type = (
            TargetType.GROUP
            if message_received.receiver in self.group_list
            else TargetType.FRIEND
        )

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
        # step2.5 check receiver availability
        if message_received.m_type < MessageType.FUNCTION:
            if message_received.t_type == TargetType.FRIEND:
                if await db_check_friend_if_blocked(
                        self.user_id, message_received.receiver,
                ): # blocked and is friend
                    message_new = Message(
                        message_id=globalMessageIdMaker.get_id(),
                        m_type=MessageType.TEXT,
                        content="This friend has been blocked!",
                        t_type=TargetType.FRIEND,
                        sender=message_received.receiver,
                        receiver=self.user_id,
                        time=int(time.time() * 1000),
                    )
                    await self.send_message_to_target(message_new, str(self.user_id))
                    return
            if message_received.receiver not in self.group_list + self.friend_list:
                return


        # step 3. publish message to persistent storage queue
        if message_received.m_type < MessageType.FUNCTION:
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
            MessageType.FUNC_MESSAGE_ADD_BROADCAST: self.rcv_add_or_del_top_message,
            MessageType.FUNC_MESSAGE_DEL_BROADCAST: self.rcv_add_or_del_top_message,
            MessageType.FUNC_RECALL_MEMBER_MESSAGE: self.rcv_callback_member_message,
            MessageType.FUNC_DELETE_MESSAGE: self.rcv_delete_message,
            MessageType.FUNC_EDIT_MESSAGE: self.rcv_edit_message,
            MessageType.FUNC_RECALL_SELF_MESSAGE: self.rcv_callback_self_message,
            MessageType.FUNC_EDIT_PROFILE: self.rcv_edit_profile,
            MessageType.FUNC_DELETE_GROUP: self.rcv_delete_group,
            MessageType.FUNC_CHANGE_GROUP_NAME: self.rcv_change_group_name,
            MessageType.FUNC_REJECT_CANDIDATE: self.rcv_reject_candidate,
        }.get(message_received.m_type, self.rcv_handle_common_message)
        await handler(message_received)

    async def rcv_create_group(self, message: Message):
        if not isinstance(message.content.members, list):
            message.content = "Wrong format"
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return None
        if len(message.content.members) == 0 and not isinstance(
                message.content.members[0], int
        ):
            message.content = "Wrong format"
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return None
        # 建群
        if self.user_id not in message.content.members:
            message.content.members = [self.user_id] + message.content.members
        group_name = message.content.name
        group_members = message.content.members
        group_list, group_id = await db_build_group(
            self.friend_list, self.user_id, group_name, group_members
        )
        message.content = group_id
        for member in group_list:
            await self.send_message_to_target(message, str(member))
        message_new = Message(
            message_id=globalMessageIdMaker.get_id(),
            m_type=MessageType.TEXT,
            content="Welcome to the group!",
            t_type=TargetType.GROUP,
            sender=self.user_id,
            receiver=group_id,
            time=int(time.time() * 1000),
            who_read=[],
        )
        message_json = message_new.model_dump_json()
        await self.storage_exchange.publish(
            aio_pika.Message(
                body=message_json.encode(),  # turn message into bytes
            ),
            routing_key="",
        )
        for member in group_list:
            await self.send_message_to_target(message_new, str(member))

    async def rcv_add_group_member(self, message: Message):
        if not isinstance(message.content, list):
            message.content = "Wrong format"
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return None
        if len(message.content) == 0 and not isinstance(message.content[0], int):
            message.content = "Wrong format"
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return None
        group_id = message.receiver
        group_add_members = message.content
        try:
            real_add_list, candidate_add_list, group_inform_list = await db_add_member(
                group_id, group_add_members, self.user_id
            )
        except KeyError as e:
            message.content = str(e)
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return None
        if len(real_add_list) > 0:  # if real add, send message to all group members
            message.content = real_add_list
            message_new = Message(
                message_id=globalMessageIdMaker.get_id(),
                m_type=MessageType.TEXT,
                content="Welcome new member to the group!",
                t_type=TargetType.GROUP,
                sender=self.user_id,
                receiver=group_id,
                time=int(time.time() * 1000),
                who_read=[],
            )
            message_json = message_new.model_dump_json()
            await self.storage_exchange.publish(
                aio_pika.Message(
                    body=message_json.encode(),  # turn message into bytes
                ),
                routing_key="",
            )
            for member in group_inform_list:
                await self.send_message_to_target(message_new, str(member))
        else:  # if not real add, send message to owner and admin
            message.content = candidate_add_list
        for member in group_inform_list:
            await self.send_message_to_target(message, str(member))

    async def rcv_reject_candidate(self, message: Message):
        group_id = message.receiver
        rejected_member = message.content
        try:
            group_inform_list = await db_reject_candidate(
                group_id, rejected_member, self.user_id
            )
        except KeyError as e:
            message.content = str(e)
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return None
        for member in group_inform_list:
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
        await self.send_message_to_target(message, str(self.user_id))
        await self.send_message_to_target(message, str(friend_id))

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
        if friend_id == self.user_id:
            message.content = "You can't block yourself"
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        friendship_now, message.content = await db_friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_friend:
            message.content = "Success"
            await self.send_message_to_target(message, str(friend_id))
            await db_friendship_change(self.user_id, friend_id, 2)
        await self.send_message_to_target(message, str(self.user_id))
        await self.send_message_to_target(message, str(friend_id))

    async def rcv_unblock_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await db_friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_block_friend:
            message.content = "Success"
            await self.send_message_to_target(message, str(friend_id))
            await db_friendship_change(self.user_id, friend_id, 1)
        await self.send_message_to_target(message, str(self.user_id))
        await self.send_message_to_target(message, str(friend_id))

    async def rcv_delete_friend(self, message: Message):
        friend_id = message.receiver
        message.sender = self.user_id
        friendship_now, message.content = await db_friendship(self.user_id, friend_id)
        if friendship_now == FriendType.already_friend:
            message.content = "Success delete"
            await self.send_message_to_target(message, str(friend_id))
            await db_friendship_change(self.user_id, friend_id, 3)
        await self.send_message_to_target(message, str(self.user_id))

    async def rcv_send_init_id(self, _: Message = None):
        contacts_info: list[int] = await db_query_fri_and_gro_id(self.user_id)
        await self.send(text_data=json.dumps(contacts_info))

    async def rcv_send_meta_info(self, _: Message = None):
        group_info: dict[int, GroupData] = await db_query_group_info(self.group_list)
        friends_id = await db_query_friends(self.user_id,if_include_block=True)
        self.friend_list = await db_query_friends(self.user_id) # update friend list
        friend_info: dict[int, UserData] = await db_query_friends_info(friends_id)
        contacts_info: dict[int, ContactsData] = {}
        contacts_info.update(group_info)
        contacts_info.update(friend_info)
        contacts_info = {key: val.model_dump() for key, val in contacts_info.items()}
        await self.send(text_data=json.dumps(contacts_info))

    async def rcv_read_message(self, message: Message):
        message_id = int(message.content)
        try:
            (
                message_sender,
                message_receiver,
                message_t_type,
            ) = await db_add_read_message(self.group_list + self.friend_list, message_id, self.user_id)
        except KeyError as e:
            message.content = str(e)
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        message.receiver = message_receiver
        message.t_type = message_t_type
        message.sender = message_sender
        await self.send_message_to_target(message, str(self.user_id))
        await self.send_message_to_target(message, str(message_sender))

    async def rcv_leave_group(self, message: Message):
        group_id = message.receiver
        user_id = self.user_id
        try:
            group_other_members = await db_reduce_person(group_id, user_id)
        except KeyError as e:
            message.content = str(e)
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        message.sender = user_id
        message.content = "user:id=" + str(user_id) + " leave group"
        for member in group_other_members:
            await self.send_message_to_target(message, str(member))
        await self.send_message_to_target(message, str(user_id))

    async def rcv_change_group_owner(self, message: Message):
        group_old_owner = self.user_id
        group_new_owner = message.receiver
        group_id = message.content
        if group_old_owner == group_new_owner:
            message.content = "You are already the owner"
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        if group_id not in self.group_list:
            message.content = "You are not in this group"
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        if group_new_owner not in self.group_members[group_id]:
            message.content = "This user is not in this group"
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        try:
            await db_change_group_owner(group_id, group_old_owner, group_new_owner)
        except KeyError as e:
            message.content = str(e)
            message.t_type = TargetType.ERROR
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
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        for member in self.group_members[group_id]:
            await self.send_message_to_target(message, str(member))

    async def rcv_remove_group_member(self, message: Message):
        group_id = message.content
        group_member = message.receiver
        try:
            await db_group_remove_member(group_id, group_member, self.user_id)
        except KeyError as e:
            message.content = str(e)
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        self.group_members[group_id].remove(group_member)
        for member in self.group_members[group_id]:
            await self.send_message_to_target(message, str(member))
        await self.send_message_to_target(message, str(group_member))

    async def rcv_add_or_del_top_message(self, message: Message):
        group_id = message.receiver
        message_id = message.content
        if message.m_type == MessageType.FUNC_MESSAGE_ADD_BROADCAST:
            if_add = True
        else:
            if_add = False
        try:
            await db_add_or_del_top_message(group_id, message_id, self.user_id, if_add)
        except KeyError as e:
            message.content = str(e)
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        for member in self.group_members[group_id]:
            await self.send_message_to_target(message, str(member))

    async def rcv_callback_member_message(self, message: Message):
        message_id = message.content
        group_id = message.receiver
        message.t_type = TargetType.GROUP
        try:
            await db_recall_member_message(
                message_id, group_id, self.user_id
            )
        except KeyError as e:
            message.content = str(e)
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        await self._forward_message(message)

    async def rcv_delete_message(self, message: Message):
        message_id = message.content
        user_id = self.user_id
        try:
            await db_delete_message(message_id, user_id)
        except KeyError as e:
            message.content = str(e)
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        await self.send_message_to_target(message, str(self.user_id))

    async def rcv_edit_message(self, message: Message):
        new_content = message.content
        user_id = self.user_id
        message_id = message.receiver
        try:
            receiver = await db_edit_message(message_id, user_id, new_content)
        except KeyError as e:
            message.content = str(e)
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        if type(receiver) == int:
            await self.send_message_to_target(message, str(receiver))
            await self.send_message_to_target(message, str(self.user_id))
        elif type(receiver) == list:
            for member in receiver:
                await self.send_message_to_target(message, str(member))

    async def rcv_callback_self_message(self, message: Message):
        message_id = message.content
        user_id = self.user_id
        try:
            await db_recall_message(message_id, user_id)
        except KeyError as e:
            message.content = str(e)
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        await self._forward_message(message)

    async def rcv_edit_profile(self, message: Message):
        message.sender = self.user_id
        message.receiver = self.user_id
        profile_get = json.loads(message.content)
        try:
            await db_edit_profile(self.user_id, profile_get)
        except KeyError as e:
            message.content = str(e)
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        await self.send_message_to_target(message, str(self.user_id))

    async def rcv_delete_group(self, message: Message):
        group_id = message.content
        try:
            group_member = await db_delete_group(group_id, self.user_id)
        except KeyError as e:
            message.content = str(e)
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        message.sender = self.user_id
        for member in group_member:
            await self.send_message_to_target(message, str(member))

    async def rcv_change_group_name(self, message: Message):
        group_id = message.receiver
        group_name = message.content
        try:
            group_list = await db_change_group_name(group_id, group_name, self.user_id)
        except KeyError as e:
            message.content = str(e)
            message.t_type = TargetType.ERROR
            await self.send_message_to_front(message)
            return
        message.sender = self.user_id
        for member in group_list:
            await self.send_message_to_target(message, str(member))

    async def rcv_handle_common_message(self, message_received: Message):
        if (    message_received.info is not None
                and "reference" in message_received.info
                and message_received.info["reference"] != -1
        ):
            reply_id = message_received.info["reference"]
            this_id = message_received.message_id
            try:
                await db_reply(self.user_id, reply_id, this_id,this_receiver=message_received.receiver)
            except KeyError as e:
                message_received.content = str(e)
                message_received.t_type = TargetType.ERROR
                await self.send_message_to_front(message_received)
                return
            else:
                message = Message(**message_received.model_dump())
                message.content = reply_id
                message.m_type = MessageType.FUNC_REPLY
                message.message_id = globalMessageIdMaker.get_id()
                await self._forward_message(message)
        if message_received.m_type != MessageType.TEXT:  # multimedia
            m_type = message_received.m_type
            md5 = message_received.content
            t_type = message_received.t_type
            user_or_group = message_received.receiver
            await db_create_multimedia(self.user_id, m_type, md5, t_type, user_or_group)
        await self._forward_message(message_received)

    async def _forward_message(self, message_received):
        if message_received.t_type == TargetType.FRIEND:  # send message to friend
            if message_received.receiver in self.friend_list:
                try:
                    if_deleted = await db_check_friend_if_deleted(self.user_id, message_received.receiver)
                except KeyError as e:
                    message_received.content = str(e)
                    message_received.t_type = TargetType.ERROR
                    await self.send_message_to_front(message_received)
                    return
                if if_deleted:
                    new_message = Message(
                        message_id=globalMessageIdMaker.get_id(),
                        content="Your friend is deleted",
                        t_type=TargetType.FRIEND,
                        m_type=MessageType.TEXT,
                        receiver=message_received.sender,
                        sender=message_received.receiver,
                        time=int(time.time() * 1000),
                        who_read=[],
                    )
                    message_json = new_message.model_dump_json()
                    await self.storage_exchange.publish(
                        aio_pika.Message(
                            body=message_json.encode(),  # turn message into bytes
                        ),
                        routing_key="",
                    )
                    await self.send_message_to_target(new_message, str(new_message.receiver))
                else:
                    await self.send_message_to_target(
                        message_received, str(message_received.receiver)
                    )
            else:
                message_received.content = "You are not friends or you are blocked or you are not in group"
                message_received.t_type = TargetType.ERROR
                await self.send_message_to_front(message_received)
                return
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
            print("pushed", retry, message.model_dump())
            self.ack_manager.manage(
                message.message_id, ack_callback, push_message(retry - 1), self.timeout
            )

        async def empty(_):
            pass

        handler: Callable[[Message], Any] = {
            MessageType.FUNC_CREATE_GROUP: self.cb_fresh_group_info,
            MessageType.FUNC_ADD_GROUP_MEMBER: self.cb_fresh_group_info,
            MessageType.FUNC_ACCEPT_FRIEND: self.cb_fresh_friend_info,
            MessageType.FUNC_DEL_FRIEND: self.cb_fresh_friend_info,
            MessageType.FUNC_BlOCK_FRIEND: self.cb_fresh_friend_info,
            MessageType.FUNC_UNBLOCK_FRIEND: self.cb_fresh_friend_info,
            MessageType.FUNC_LEAVE_GROUP: self.cb_fresh_group_info,
            MessageType.FUNC_CHANGE_GROUP_OWNER: self.cb_fresh_group_info,
            MessageType.FUNC_ADD_GROUP_ADMIN: self.cb_fresh_group_info,
            MessageType.FUNC_REMOVE_GROUP_ADMIN: self.cb_fresh_group_info,
            MessageType.FUNC_REMOVE_GROUP_MEMBER: self.cb_fresh_group_info,
            MessageType.FUNC_DELETE_GROUP: self.cb_fresh_group_info,
        }.get(message.m_type, empty)
        await handler(message)

        await push_message()


    async def cb_fresh_friend_info(self, _: Message):
        self.friend_list = await db_query_friends(self.user_id)

    async def cb_fresh_group_info(self, _: Message):
        await self.fresh_group_info()

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

    async def cb_pass_message(self, message: Message):
        pass
