import enum

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
    FUNC_EXIT_GROUP = 9
    FUNC_APPLY_FRIEND = 10
    FUNC_ACCEPT_FRIEND = 11
    FUNC_REJECT_FRIEND = 12
    FUNC_BlOCK_FRIEND = 13
    FUNC_DEL_FRIEND = 14
    FUNC_READ_MSG = 15
    FUNC_UPDATE_SETTINGS = 16   # includes updating ANY user settings (e.g. mute contact / change email)


class TargetType(enum.IntEnum):
    FRIEND = 0
    GROUP = 1
    OTHER = 2


class ContactsData(BaseModel):
    id: int
    name: str
    avatar: str
    category: str


class UserData(ContactsData):
    email: str
    category: str = "user"


class GroupData(ContactsData):
    members: list[UserData|int]
    category: str = "group"


class Message(BaseModel):
    message_id: int | str = None    # str if id is temporary
    m_type: MessageType = MessageType.TEXT
    t_type: TargetType = TargetType.OTHER
    time: int = None  # write by backend
    content: str | list | int | GroupData | UserData  # 如果是消息，content 是 str，如果是函数，content 是 list,如果是群加人，这个放群id
    sender: int = None  # 如果是消息，sender 是发送者的 id，如果是函数，sender 是函数的发起者的 id。如果是群加人，这个放拉人的人
    receiver: int | None = None  # 如果是消息，receiver 是接收者的 id，如果是函数，receiver 是函数的接收者的 id。如果是群加人，这个放被拉的人
    info: str | None = None  # for message referencing, forwarding and appending info


class Ack(BaseModel):
    message_id: int  # real unique id
    reference: str | None = None  # temporary id
