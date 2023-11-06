import json
import os
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from users.models import User, Friendship
from files.models import Multimedia
from utils.utils_jwt import hash_string_with_sha256, generate_jwt_token
from utils.utils_request import request_failed, request_success, BAD_METHOD
from utils.utils_require import check_require, CheckRequire, require


# Create your views here.
@CheckRequire
@csrf_exempt  # 允许跨域,便于测试
def upload(req: HttpRequest, hash_code: str):
    # check the method
    if req.method != "POST":
        return BAD_METHOD
    multimedia_content = req.body
    multimedia_md5 = hash_code
    # calculate the md5 of the content
    real_md5 = hash_string_with_sha256(multimedia_content, num_iterations=5)
    if real_md5 != multimedia_md5:
        return request_failed(2, "the md5 is not correct", status_code=401)
    if Multimedia.objects.filter(multimedia_id=real_md5).exists():
        # if the file exists,do nothing,else download the file
        if not os.path.exists("./files"):
            os.mkdir("./files")
        file_path = "./files/" + real_md5
        if not os.path.exists(file_path):
            with open(file_path, "w") as f:
                f.write(multimedia_content)
        return request_success()
    else:
        # if the file does not exist.
        return request_failed(2, "you can not post the file without claim in websocket", status_code=401)


@CheckRequire
@csrf_exempt  # 允许跨域,便于测试
def download(req: HttpRequest, hash_code: str):
    if req.method != "GET":
        return BAD_METHOD
    user_id = req.user_id  # get the user id
    multimedia_md5 = hash_code
    if Multimedia.objects.filter(multimedia_id=multimedia_md5).exists():
        multimedia = Multimedia.objects.get(multimedia_id=multimedia_md5)
        user_list = multimedia.multimedia_user_listener
        group_list = multimedia.multimedia_group_listener
        listener = False
        if user_id in user_list:
            listener = True
        for group in group_list:
            if user_id in group.group_members:
                listener = True
        if not listener:
            return request_failed(2, "you can not get this file", status_code=401)
        else:
            if not os.path.exists("./files"):
                os.mkdir("./files")
            file_path = "./files/" + multimedia_md5
            if not os.path.exists(file_path):
                return request_failed(2, "the file is not in the server", status_code=401)
            else:
                with open(file_path, "r") as f:
                    multimedia_content = f.read()
                response_data = {
                    "multimediaContent": multimedia_content,
                    "multimediaType": multimedia.multimedia_type
                }
                return request_success(response_data)
    else:
        return request_failed(2, "the file hasn't claim", status_code=401)
