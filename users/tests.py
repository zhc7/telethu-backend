from django.test import TestCase
from django.urls import reverse
from users.models import User, Friendship, MessageList, GroupList
from utils.utils_jwt import hash_string_with_sha256


class UserTestCase(TestCase):
    def setUp(self):
        self.user1 = User.objects.create(
            username="test1",
            userEmail="test1@qq.com",
            password=hash_string_with_sha256("test1", num_iterations=5),
            avatar="22933c1646d1f0042e39d7471e42f33b",
            profile='{"gender": "male", "age": 20}',
        )
        self.user2 = User.objects.create(
            username="test2",
            userEmail="test2@qq.com",
            password=hash_string_with_sha256("test2", num_iterations=5),
            avatar="22933c1646d1f0042e39d7471e42f33b",
            profile='{"gender": "male", "age": 20}',
        )
        self.user1_token = None
        self.user2_token = None

    def test_login_success(self):
        # 尝试登录
        response = self.client.post(
            reverse("login"),
            {"userEmail": self.user1.userEmail, "password": "test1"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"], "Succeed")
        self.user1_token = response.json()["token"]

    def test_login_wrong_password(self):
        response = self.client.post(
            reverse("login"),
            {"userEmail": self.user1.userEmail, "password": "wrong_password"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["info"], "Wrong password")

    def test_login_wrong_email(self):
        response = self.client.post(
            reverse("login"),
            {"userEmail": "wrong_Email", "password": "test1"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["info"], "User not exists")

    def test_login_without_password(self):
        response = self.client.post(
            reverse("login"),
            {"userEmail": self.user1.userEmail},
            content_type="application/json",
        )
        print(response.json())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["info"], "Missing or error type of [password]")

    def test_login_without_email(self):
        response = self.client.post(
            reverse("login"),
            {"password": "test1"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["info"], "Missing or error type of [email]")

    def test_login_wrong_method(self):
        response = self.client.get(
            reverse("login"),
            {"userEmail": self.user1.userEmail, "password": "test1"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["info"], "Bad method")

    def test_login_repeat(self):
        self.client.post(
            reverse("login"),
            {"userEmail": self.user1.userEmail, "password": "test1"},
            content_type="application/json",
        )
        response = self.client.post(
            reverse("login"),
            {"userEmail": self.user1.userEmail, "password": "test1"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["info"], "Login failed because some user has login"
        )
