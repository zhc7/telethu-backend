from django.test import TestCase
from files.models import Multimedia
from users.models import User
from utils.utils_jwt import hash_string_with_sha256
from django.urls import reverse


# Create your tests here.
class FilesTestCase(TestCase):
    def setUp(self):
        self.user1 = User.objects.create(
            username="test1",
            userEmail="test1@qq.com",
            password=hash_string_with_sha256("test1", num_iterations=5),
            avatar="22933c1646d1f0042e39d7471e42f33b",
            profile='{"gender": "male", "age": 20}',
        )
        self.mul = Multimedia.objects.create(
            multimedia_id="22933c1646d1f0042e39d7471e42f33b", multimedia_type=0
        )
        self.mul.multimedia_user_listener.add(self.user1)

    def test_load(self):
        response = self.client.post(
            reverse("login"),
            {"userEmail": self.user1.userEmail, "password": "test1"},
            content_type="application/json",
        )
        # get
        self.assertEqual(response.status_code, 200)
        response = self.client.get(
            reverse("load", kwargs={"hash_code": "22933c1646d1f0042e39d7471e42f33b"}),
            content_type="application/json",
        )
        picture = response.content
        self.assertEqual(response.status_code, 200)
        # post
        response = self.client.post(
            reverse("load", kwargs={"hash_code": "22933c1646d1f0042e39d7471e42f33b"}),
            picture,
            content_type="png",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info"], "Succeed")
