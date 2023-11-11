from django.db import models
from threading import Lock


class User(models.Model):
    id = models.AutoField(
        primary_key=True
    )  # If necessary, change the AutoField to BigAutoField.
    username = models.CharField(max_length=32)
    password = models.CharField(max_length=128)
    userEmail = models.EmailField(unique=True, max_length=128)
    avatar = models.CharField(
        max_length=256,
        default="https://images.unsplash.com/photo-1642921131008-b13897b36d17?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxzZWFyY2h8MXx8JUU2JUI4JTg1JUU1JThEJThFJUU1JUE0JUE3JUU1JUFEJUE2fGVufDB8fDB8fHww&auto=format&fit=crop&w=800&q=60",
    )
    created_time = models.DateTimeField(auto_now_add=True)
    verification = models.BooleanField(default=False)
    profile = models.JSONField(default=dict)

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


class GroupList(models.Model):
    group_id = models.AutoField(primary_key=True)
    group_name = models.CharField(max_length=32, default="群聊")
    created_time = models.DateTimeField(auto_now_add=True)
    group_avatar = models.CharField(
        max_length=256,
        default="https://images.unsplash.com/photo-1642921131008-b13897b36d17?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxzZWFyY2h8MXx8JUU2JUI4JTg1JUU1JThEJThFJUU1JUE0JUE3JUU1JUFEJUE2fGVufDB8fDB8fHww&auto=format&fit=crop&w=800&q=60",
    )
    group_members = models.ManyToManyField(User, related_name="group_members")
    # 群主管理员之后再加
    # group_admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='group_admin')


class MessageList(models.Model):
    message_id = models.AutoField(primary_key=True)
    m_type = models.IntegerField(blank=False, null=False)
    t_type = models.IntegerField(blank=False, null=False)
    time = models.BigIntegerField(blank=False, null=False)
    content = models.TextField()
    sender = models.IntegerField(blank=False, null=False)
    receiver = models.IntegerField(blank=False, null=False)
    info = models.CharField(max_length=256, default="")
