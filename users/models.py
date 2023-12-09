from django.db import models
from utils.data import MessageStatusType


class User(models.Model):
    id = models.AutoField(
        primary_key=True
    )  # If necessary, change the AutoField to BigAutoField.
    username = models.CharField(max_length=32)
    password = models.CharField(max_length=128)
    userEmail = models.EmailField(unique=True, max_length=128)
    avatar = models.CharField(
        max_length=256,
        default="22933c1646d1f0042e39d7471e42f33b",
    )
    created_time = models.DateTimeField(auto_now_add=True)
    verification = models.BooleanField(default=False)
    profile = models.JSONField(default=dict)
    is_deleted = models.BooleanField(
        default=False
    )  # If the user is deleted, default not to be deleted.

    class Meta:
        pass

    def serialize(self):
        return {
            "id": self.id,
            "username": self.username,
            "created_time": self.created_time,
            "email": self.userEmail,
            "avatar": self.avatar,
        }

    def __str__(self):
        return str(self.id)


class Friendship(models.Model):  # 好友关系
    # user1 为发起者 user2 为接受者
    user1 = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user1_friendships"
    )
    user2 = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user2_friendships"
    )
    created_time = models.DateTimeField(auto_now_add=True)
    state = models.IntegerField(default=0)  # 0: 申请中 1: 已同意 2: 已拉黑 3: 已拒绝

    class Meta:
        unique_together = [["user1", "user2"]]

    def __str__(self):
        return f"{self.user1} - {self.user2} Friendship"


class MessageList(models.Model):
    message_id = models.AutoField(primary_key=True)
    m_type = models.IntegerField(blank=False, null=False)
    t_type = models.IntegerField(blank=False, null=False)
    time = models.BigIntegerField(blank=False, null=False)
    content = models.TextField()
    sender = models.IntegerField(blank=False, null=False)
    receiver = models.IntegerField(blank=False, null=True)
    info = models.CharField(max_length=256, default="", blank=True, null=True)
    who_read = models.ManyToManyField(User, related_name="who_read")
    deleted_users = models.ManyToManyField(User, related_name="deleted_users")
    status = models.IntegerField(
        default=MessageStatusType.NORMAL,
    )


class GroupList(models.Model):
    group_id = models.AutoField(primary_key=True)
    group_name = models.CharField(max_length=32, default="群聊")
    created_time = models.DateTimeField(auto_now_add=True)
    group_avatar = models.CharField(
        max_length=256,
        default="22933c1646d1f0042e39d7471e42f33b",
    )
    group_members = models.ManyToManyField(User, related_name="group_members")
    # # 群主
    group_owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="group_owner", null=True
    )
    # # 群管理员
    group_admin = models.ManyToManyField(User, related_name="group_admin")
    # 置顶消息
    group_top_message = models.ManyToManyField(
        MessageList, related_name="group_top_message"
    )
