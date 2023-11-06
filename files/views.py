import json
import os
from django.http import HttpRequest, FileResponse
from django.views.decorators.csrf import csrf_exempt
import hashlib
from users.models import User, Friendship
from files.models import Multimedia
from utils.utils_jwt import hash_string_with_sha256, generate_jwt_token
from utils.utils_request import request_failed, request_success, BAD_METHOD
from utils.utils_require import check_require, CheckRequire, require


# Create your views here.
@CheckRequire
@csrf_exempt  # 允许跨域,便于测试
def load(req: HttpRequest, hash_code: str):
    # check the method
    if req.method == "POST":
        multimedia_content = req.body
        multimedia_md5 = hash_code
        # calculate the md5 of the content
        md5_hash = hashlib.md5()
        md5_hash.update(multimedia_content)
        real_md5 = md5_hash.hexdigest()
        # 获取 MD5 哈希值的十六进制表示
        md5_hex = md5_hash.hexdigest()
        if real_md5 != multimedia_md5:
            return request_failed(2, "the md5 is not correct", status_code=401)
        if Multimedia.objects.filter(multimedia_id=real_md5).exists():
            # if the file exists,do nothing,else download the file
            if not os.path.exists("./files/file_storage"):
                os.mkdir("./files/file_storage")

            file_path = "./files/file_storage/" + real_md5
            if not os.path.exists(file_path):
                with open(file_path, "wb") as f:
                    f.write(multimedia_content)
            return request_success()
        else:
            # if the file does not exist.
            return request_failed(
                2, "you can not post the file without claim in websocket", status_code=401
            )
    elif req.method == "GET":
        user_id = req.user_id  # get the user id
        multimedia_md5 = hash_code
        if Multimedia.objects.filter(multimedia_id=multimedia_md5).exists():
            multimedia = Multimedia.objects.get(multimedia_id=multimedia_md5)
            user_list = multimedia.multimedia_user_listener
            group_list = multimedia.multimedia_group_listener
            listener = False
            if user_list is not None and user_list.filter(id=user_id).exists():
                listener = True
            if group_list is not None:
                groups = group_list.all()
                for group in groups:
                    if user_id in group.group_members:
                        listener = True
            if not listener:
                return request_failed(2, "you can not get this file", status_code=401)
            else:
                if not os.path.exists("./files/file_storage"):
                    os.mkdir("./files/file_storage")
                file_path = "./files/file_storage/" + multimedia_md5
                if not os.path.exists(file_path):
                    return request_failed(
                        2, "the file is not in the server", status_code=401
                    )
                else:
                    with open(file_path, "rb") as f:
                        multimedia_content = f.read()
                    response = FileResponse(
                        multimedia_content, content_type="application/octet-stream"
                    )
                    response["Content-Disposition"] = "attachment"
                    return response
        else:
            return request_failed(2, "the file hasn't claim", status_code=401)
    else:
        return BAD_METHOD

