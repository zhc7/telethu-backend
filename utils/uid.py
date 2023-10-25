from threading import Lock
from users.models import User, GroupList, MessageList


class IdMaker:
    def __init__(self):
        self.lock = Lock()
        # 查找当前数据库中最大的 id，包括group_id和user_id
        max_id = max(User.objects.all().values_list('id', flat=True) or [0])
        if max_id is None:
            max_id = 0
        max_group_id = max(GroupList.objects.all().values_list('group_id', flat=True) or [0])
        if max_group_id is None:
            max_group_id = 0
        self.id = max(max_id, max_group_id)

    def get_id(self):
        with self.lock:
            self.id += 1
        return self.id


# 使用globalIdMaker进行全局id生成，控制id的唯一性
globalIdMaker = IdMaker()

# TODO: 为所有的消息做一个上面的 id_maker
class MessageIdMaker:
    def __init__(self):
        self.lock = Lock()
        # 查找当前数据库中最大的 id，包括group_id和user_id
        max_id = max(MessageList.objects.all().values_list('message_id', flat=True) or [0])
        if max_id is None:
            max_id = 0
        self.id = max_id

    def get_id(self):
        with self.lock:
            self.id += 1
        return self.id


globalMessageIdMaker = MessageIdMaker()