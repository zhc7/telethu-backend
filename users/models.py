from django.db import models


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
        return self.username


class Friendship(models.Model): # 好友关系
    # user1 为发起者 user2 为接受者
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user1_friendships')
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user2_friendships')
    created_time = models.DateTimeField(auto_now_add=True)
    state = models.IntegerField(default=0) # 0: 申请中 1: 已同意 2: 已拉黑 3: 已拒绝

    class Meta:
        unique_together = [['user1', 'user2']]

    def __str__(self):
        return f'{self.user1} - {self.user2} Friendship'
