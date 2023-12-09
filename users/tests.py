import hashlib

from django.test import TestCase
from django.urls import reverse
from users.models import User, Friendship, GroupList, MessageList
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
        self.assertEqual(response.status_code, 405)
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

    def test_register_success(self):
        response = self.client.post(
            reverse("register"),
            {
                "userEmail": "test4@qq.com",
                "userName": "test4",
                "password": "test4",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"], "Succeed")

    def test_register_without_email(self):
        response = self.client.post(
            reverse("register"),
            {
                "userName": "test4",
                "password": "test4",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["info"], "Missing or error type of [email]")

    def test_register_without_username(self):
        response = self.client.post(
            reverse("register"),
            {
                "userEmail": "test4@qq.com",
                "password": "test4",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["info"], "Missing or error type of [userName]")

    def test_register_without_password(self):
        response = self.client.post(
            reverse("register"),
            {
                "userEmail": "test4@qq.com",
                "userName": "test4",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["info"], "Missing or error type of [password]")

    def test_register_wrong_method(self):
        response = self.client.get(
            reverse("register"),
            {
                "userEmail": "test4@qq.com",
                "userName": "test4",
                "password": "test4",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["info"], "Bad method")

    def test_register_repeat(self):
        self.client.post(
            reverse("register"),
            {
                "userEmail": "test1@qq.com",
                "userName": "test1",
                "password": "test1",
            },
            content_type="application/json",
        )
        response = self.client.post(
            reverse("register"),
            {
                "userEmail": "test1@qq.com",
                "userName": "test1",
                "password": "test1",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["info"], "userEmail already exists")

    def test_logout_success(self):
        self.client.post(
            reverse("login"),
            {"userEmail": self.user1.userEmail, "password": "test1"},
            content_type="application/json",
        )
        response = self.client.post(
            reverse("logout"),
            {"userEmail": self.user1.userEmail, "password": "test1"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"], "Succeed")

    def test_get_user_info_user_success(self):
        self.client.post(
            reverse("login"),
            {"userEmail": self.user1.userEmail, "password": "test1"},
            content_type="application/json",
        )
        response = self.client.get(
            reverse("get_user_info", kwargs={"user_id": self.user1.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"], "Succeed")
        self.assertEqual(response.json()["name"], "test1")
        self.assertEqual(response.json()["email"], "test1@qq.com")
        self.assertEqual(response.json()["avatar"], "22933c1646d1f0042e39d7471e42f33b")

    def test_get_user_info_group_success(self):
        GroupList.objects.create(group_name="test_group", group_avatar="22933c1646d1f0042e39d7471e42f33b", group_owner=self.user1, group_id=10)
        MessageList.objects.create(m_type=1, t_type=1, time=1, content="test", sender=self.user1.id, receiver=10, message_id=11)
        group = GroupList.objects.get(group_id=10)
        self.client.post(
            reverse("login"),
            {"userEmail": self.user1.userEmail, "password": "test1"},
            content_type="application/json",
        )
        response = self.client.get(
            reverse("get_user_info", kwargs={"user_id": 10}),
            content_type="application/json",
        )
        print("----------------------------------")
        print(response.json())
        print("----------------------------------")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"], "Succeed")
        self.assertEqual(response.json()["name"], "test_group")
        self.assertEqual(response.json()["avatar"], "22933c1646d1f0042e39d7471e42f33b")
        self.assertEqual(response.json()["top_message"][0], 11)




    def test_get_friend_list_success(self):
        Friendship.objects.create(user1=self.user1, user2=self.user2, state=1)
        self.client.post(
            reverse("login"),
            {"userEmail": self.user1.userEmail, "password": "test1"},
            content_type="application/json",
        )
        response = self.client.get(
            reverse("get_friend_list"),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"], "Succeed")
        self.assertEqual(response.json()["friends"][0]["email"], "test2@qq.com")
        self.assertEqual(
            response.json()["friends"][0]["avatar"], "22933c1646d1f0042e39d7471e42f33b"
        )

    def test_get_apply_list(self):
        Friendship.objects.create(user1=self.user1, user2=self.user2, state=0)
        self.client.post(
            reverse("login"),
            {"userEmail": self.user2.userEmail, "password": "test2"},
            content_type="application/json",
        )
        response = self.client.get(
            reverse("get_apply_list"),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"], "Succeed")
        self.assertEqual(response.json()["friends"][0]["name"], "test1")
        self.assertEqual(response.json()["friends"][0]["email"], "test1@qq.com")
        self.assertEqual(
            response.json()["friends"][0]["avatar"], "22933c1646d1f0042e39d7471e42f33b"
        )

    def test_get_you_apply_list(self):
        Friendship.objects.create(user1=self.user1, user2=self.user2, state=0)
        self.client.post(
            reverse("login"),
            {"userEmail": self.user1.userEmail, "password": "test1"},
            content_type="application/json",
        )
        response = self.client.get(
            reverse("get_you_apply_list"),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"], "Succeed")
        self.assertEqual(response.json()["friends"][0]["name"], "test2")
        self.assertEqual(response.json()["friends"][0]["email"], "test2@qq.com")
        self.assertEqual(
            response.json()["friends"][0]["avatar"], "22933c1646d1f0042e39d7471e42f33b"
        )

    def test_verify_success(self):
        # TODO: zry来写这个测试
        pass

    def test_sendemail_success(self):
        # TODO: zry来写这个测试
        pass

    def test_avatar_success(self):
        self.client.post(
            reverse("login"),
            {"userEmail": self.user1.userEmail, "password": "test1"},
            content_type="application/json",
        )
        response = self.client.get(
            reverse("avatar", kwargs={"hash_code": "22933c1646d1f0042e39d7471e42f33b"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        picture = response.content
        md5_hash = hashlib.md5()
        md5_hash.update(picture)
        real_md5 = md5_hash.hexdigest()
        self.assertEqual(real_md5, "22933c1646d1f0042e39d7471e42f33b")
        # 再传上去
        response = self.client.post(
            reverse("avatar"),
            picture,
            content_type="png",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"], "Succeed")

    def test_profile_success(self):
        self.client.post(
            reverse("login"),
            {"userEmail": self.user1.userEmail, "password": "test1"},
            content_type="application/json",
        )
        response = self.client.post(
            reverse("profile"),
            {"userEmail": "test1@qq.com", "password": "test1"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"], "Succeed")

        response = self.client.get(
            reverse("profile"),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["userEmail"], "test1@qq.com")
        self.assertEqual(response.json()["password"], "test1")

    def test_user_search_success(self):
        self.client.post(
            reverse("login"),
            {"userEmail": self.user1.userEmail, "password": "test1"},
            content_type="application/json",
        )
        response = self.client.post(
            reverse("user_search"),
            {"info": "test2", "type": "1"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"], "Succeed")
        self.assertEqual(response.json()["users"][0]["name"], "test2")
        self.assertEqual(response.json()["users"][0]["email"], "test2@qq.com")
        response = self.client.post(
            reverse("user_search"),
            {"info": "1", "type": "0"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"], "Succeed")
        self.assertEqual(response.json()["users"][0]["name"], "test1")
        self.assertEqual(response.json()["users"][0]["email"], "test1@qq.com")

    def test_delete_user_success(self):
        response = self.client.post(
            reverse("login"),
            {"userEmail": self.user2.userEmail, "password": "test2"},
            content_type="application/json",
        )
        token = response.json()["token"]
        response = self.client.delete(
            reverse("delete_user"),
            {"token": token},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"], "Succeed")
