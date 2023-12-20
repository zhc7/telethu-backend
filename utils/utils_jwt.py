import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from users.models import User

SALT = "DeepDarkFantasy".encode("utf-8")
EXPIRE_IN_SECONDS = 60 * 60 * 24 * 1  # 1 day
ALT_CHARS = "-_".encode("utf-8")

# 这里是后端鉴权当中 JWT 相关的部分。初步使用的是与小作业中一样的鉴权方法，只是改变了 SALT 。


def hash_string_with_sha256(input_string, num_iterations=1):
    hashed_string = input_string.encode("utf-8")

    for _ in range(num_iterations):
        hashed_string = hashlib.sha256(SALT + hashed_string).digest()

    # 将最终结果以十六进制字符串返回
    return hashed_string.hex()


def b64url_encode(s):
    if isinstance(s, str):
        return base64.b64encode(s.encode("utf-8"), altchars=ALT_CHARS).decode("utf-8")
    else:
        return base64.b64encode(s, altchars=ALT_CHARS).decode("utf-8")


def b64url_decode(s: str, decode_to_str=True):
    if decode_to_str:
        return base64.b64decode(s, altchars=ALT_CHARS).decode("utf-8")
    else:
        return base64.b64decode(s, altchars=ALT_CHARS)


def sign(*parts):
    raw = ".".join(parts)
    signature = hmac.new(SALT, raw.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return b64url_encode(signature)


def generate_jwt_token(user_id: str):
    # * header
    header = {"alg": "HS256", "typ": "JWT"}
    # dump to str. remove `\n` and space after `:`
    header_str = json.dumps(header, separators=(",", ":"))
    # use base64url to encode, instead of base64
    header_b64 = b64url_encode(header_str)

    # * payload
    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + EXPIRE_IN_SECONDS,
        "data": {
            "user_id": user_id,
        },
    }
    payload_str = json.dumps(payload, separators=(",", ":"))
    payload_b64 = b64url_encode(payload_str)

    # * signature
    password = User.objects.filter(id=user_id)[0].password
    signature_b64 = sign(header_b64, payload_b64, password)

    return header_b64 + "." + payload_b64 + "." + signature_b64


def check_jwt_token(token: str) -> Optional[dict]:
    # * Split token
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        payload_str = b64url_decode(payload_b64)
        payload = json.loads(payload_str)

        # * Check signature
        user_id = payload["data"]["user_id"]
        password = User.objects.filter(id=user_id)[0].password
        signature_b64_check = sign(header_b64, payload_b64, password)
        if signature_b64_check != signature_b64:
            return None

        # Check expire
        if payload["exp"] < time.time():
            return None
        if not User.objects.filter(id=user_id).exists():
            return None
        return user_id
    except:
        return None
