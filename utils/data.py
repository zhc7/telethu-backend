import enum
from enum import IntFlag, auto
from pydantic import BaseModel


class MessageType(enum.IntEnum):
    TEXT = 0
    IMAGE = 1
    AUDIO = 2
    VIDEO = 3
    FILE = 4
    STICKER = 5
    FUNCTION = (
        6  # this marks the line between message and function, do not set this directly
    )
    FUNC_CREATE_GROUP = 7
    FUNC_ADD_GROUP_MEMBER = 8
    FUNC_RECALL_SELF_MESSAGE = 9
    FUNC_APPLY_FRIEND = 10
    FUNC_ACCEPT_FRIEND = 11
    FUNC_REJECT_FRIEND = 12
    FUNC_BlOCK_FRIEND = 13
    FUNC_DEL_FRIEND = 14
    FUNC_CHANGE_GROUP_OWNER = 15
    FUNC_UPDATE_SETTINGS = (
        16  # includes updating ANY user settings (e.g. mute contact / change email)
    )
    FUNC_UNBLOCK_FRIEND = 17
    FUNC_SEND_META = 18
    FUNC_READ_MESSAGE = 19
    FUNC_LEAVE_GROUP = 20
    FUNC_ADD_GROUP_ADMIN = 21
    FUNC_REMOVE_GROUP_ADMIN = 22
    FUNC_REMOVE_GROUP_MEMBER = 23
    FUNC_MESSAGE_ADD_BROADCAST = 24
    FUNC_MESSAGE_DEL_BROADCAST = 25
    FUNC_RECALL_MEMBER_MESSAGE = 26
    FUNC_DELETE_MESSAGE = 27
    FUNC_EDIT_MESSAGE = 28
    FUNC_EDIT_PROFILE = 29
    FUNC_DELETE_GROUP = 30


class TargetType(enum.IntEnum):
    FRIEND = 0
    GROUP = 1
    OTHER = 2
    ERROR = 3


class ContactsData(BaseModel):
    id: int | None = None
    name: str
    avatar: str
    category: str


class UserData(ContactsData):
    email: str
    category: str = "user"


class GroupData(ContactsData):
    top_message: list[int] | None = None
    members: list[int]
    owner: int | None = None
    admin: list[int] | None = None
    category: str = "group"


class Message(BaseModel):
    message_id: int | str = None  # str if id is temporary
    m_type: MessageType = MessageType.TEXT
    t_type: TargetType = TargetType.OTHER
    time: float = None  # write by backend
    content: str | list | int | GroupData | UserData   # 如果是消息，content 是 str，如果是函数，content 是 list,如果是群加人，这个放群id
    sender: int = None  # 如果是消息，sender 是发送者的 id，如果是函数，sender 是函数的发起者的 id。如果是群加人，这个放拉人的人
    receiver: int | None = (
        None  # 如果是消息，receiver 是接收者的 id，如果是函数，receiver 是函数的接收者的 id。如果是群加人，这个放被拉的人
    )
    info: str | list | dict | None = (
        None  # for message referencing, forwarding and appending info
    )
    who_read: bool | list | None = (
        None  # list for group chat, bool for personal chat
    )


class Ack(BaseModel):
    message_id: int  # real unique id
    reference: str | None = None  # temporary id


class FriendType(enum.IntEnum):
    user_equal_friend = 0
    already_friend = 1
    already_send_apply = 2
    already_receive_apply = 3
    already_block_friend = 4
    already_been_block = 5
    already_reject_friend = 6
    already_been_reject = 7
    relationship_not_exist = 8
    friend_not_exist = 9


class MessageStatusType(IntFlag):
    NORMAL = auto()
    RECALLED = auto()
    EDITED = auto()
