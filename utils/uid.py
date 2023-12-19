from threading import Lock
from users.models import User, GroupList, MessageList, MaxId


class IdMaker:
    def __init__(self):
        self.lock = Lock()
        self.id = None
        self.initialized = False

    def late_init(self):
        # 查找当前数据库中最大的 id，包括group_id和user_id
        max_id = max(User.objects.all().values_list("id", flat=True) or [0])
        if max_id is None:
            max_id = 0
        max_group_id = max(
            GroupList.objects.all().values_list("group_id", flat=True) or [0]
        )
        if max_group_id is None:
            max_group_id = 0
        self.id = max(max_id, max_group_id)
        max_id_value = MaxId.objects.first()
        if max_id_value is None:
            max_id_value = MaxId(max_id_value=self.id)
            max_id_value.save()
        else:
            if max_id_value.max_id_value < self.id:
                max_id_value.max_id_value = self.id
                max_id_value.save()
            else:
                self.id = max_id_value.max_id_value
        self.initialized = True

    def get_id(self):
        if not self.initialized:
            self.late_init()
        with self.lock:
            self.id += 1
        max_id_value = MaxId.objects.first()
        max_id_value.max_id_value = self.id
        max_id_value.save()
        return self.id


# 使用globalIdMaker进行全局id生成，控制id的唯一性
globalIdMaker = IdMaker()


# TODO: 为所有的消息做一个上面的 id_maker
class MessageIdMaker:
    def __init__(self):
        self.id = None
        self.lock = Lock()

    def late_init(self):
        # 查找当前数据库中最大的 id，包括group_id和user_id
        max_id = max(
            MessageList.objects.all().values_list("message_id", flat=True) or [0]
        )
        if max_id is None:
            max_id = 0
        self.id = max_id

    def get_id(self):
        with self.lock:
            self.id += 1
        return self.id


globalMessageIdMaker = MessageIdMaker()
