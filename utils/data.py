import enum

from pydantic import BaseModel


class MessageType(enum.IntEnum):
    TEXT = 0
    IMAGE = 1
    AUDIO = 2
    VIDEO = 3
    FILE = 4
    FUNCTION = (
        5  # this marks the line between message and function, do not set this directly
    )
    FUNC_ADD_FRIEND = 6
    FUNC_CREATE_GROUP = 7
    FUNC_ADD_GROUP_MEMBER = 8


class TargetType(enum.IntEnum):
    FRIEND = 0
    GROUP = 1
    OTHER = 2


class Message(BaseModel):
    message_id: int
    m_type: MessageType = MessageType.TEXT
    t_type: TargetType = TargetType.OTHER
    time: float
    content: str | list | int  # 如果是消息，content 是 str，如果是函数，content 是 list,如果是群加人，这个放群id
    sender: int  # 如果是消息，sender 是发送者的 id，如果是函数，sender 是函数的发起者的 id。如果是群加人，这个放拉人的人
    receiver: int  # 如果是消息，receiver 是接收者的 id，如果是函数，receiver 是函数的接收者的 id。如果是群加人，这个放被拉的人
    info: str  # for message referencing, forwarding and appending info


class ContactsData(BaseModel):
    id: int
    name: str
    avatar: str
    category: str


class UserData(ContactsData):
    email: str
    category: str = "user"


class GroupData(ContactsData):
    members: list[UserData]
    category: str = "group"
