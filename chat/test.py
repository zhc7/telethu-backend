from django.test import TestCase
from files.models import Multimedia
from users.models import User, MessageList
from utils.utils_jwt import hash_string_with_sha256
from django.urls import reverse
class HistoryTestCase(TestCase):
    def setUp(self):
        # TODO: zry
        self.user1 = User.objects.create(
            username="test1",
            userEmail="test1@qq.com",
            password=hash_string_with_sha256("test1", num_iterations=5),
            avatar="22933c1646d1f0042e39d7471e42f33b",
            profile='{"gender": "male", "age": 20}',
        )

    def test_history(self):
        # TODO: zry
        pass

    def test_filter(self):
        # TODO: zry
        pass

    def test_message_success(self):
        # login
        response = self.client.post(
            reverse("login"),
            {"userEmail": self.user1.userEmail, "password": "test1"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        token = response.json()["token"]
        MessageList.objects.create(
            message_id=1,
            m_type=0,
            t_type=0,
            time=0,
            content="test",
            sender=1,
            receiver=2,
            info="test",
        )
        msg = MessageList.objects.get(message_id=1)
        msg.who_read.add(1)
        response = self.client.get(
            reverse("message", kwargs={"message_id": 1}),
            {"token": token},
            content_type="application/json",
        )
        print("---------------")
        print(response.json())
        print("---------------")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "test")
