import secrets

from django.db import models


class User(models.Model):
    id = models.AutoField(primary_key=True)  # If necessary, change the AutoField to BigAutoField.
    username = models.CharField(max_length=32, unique=True)
    password = models.CharField(max_length=128)
    # phone = models.CharField(max_length=16, unique=True)
    avatar = models.CharField(max_length=256,
                              default="https://images.unsplash.com/photo-1642921131008-b13897b36d17?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxzZWFyY2h8MXx8JUU2JUI4JTg1JUU1JThEJThFJUU1JUE0JUE3JUU1JUFEJUE2fGVufDB8fDB8fHww&auto=format&fit=crop&w=800&q=60")
    created_time = models.DateTimeField(auto_now_add=True)
    token = models.CharField(max_length=64, null=True, unique=True)

    class Meta:
        pass

    def serialize(self):
        return {
            "id": self.id,
            "username": self.username,
            "created_time": self.created_time,
            # "phone": self.phone,
            "avatar": self.avatar,
        }

    def __str__(self):
        return self.username

    def generate_token(self):
        # 生成一个随机令牌
        token = secrets.token_hex(32)
        self.token = token
        self.save()
        return token
