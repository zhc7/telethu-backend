from functools import wraps
from utils.utils_request import request_failed

MAX_CHAR_LENGTH = 255


# Here err_code == -2 denotes "Error in request body"
# And err_code == -1 denotes "Error in request URL parsing"
def require(body, key, types="string", err_msg=None, err_code=401):
    if key not in body.keys():
        raise KeyError(
            err_msg
            if err_msg is not None
            else f"Invalid parameters. Expected `{key}`, but not found.",
            err_code,
        )

    val = body[key]

    err_msg = (
        f"Invalid parameters. Expected `{key}` to be `{types}` type."
        if err_msg is None
        else err_msg
    )

    if types == "int":
        try:
            val = int(val)
            return val
        except ValueError:
            raise KeyError(err_msg, err_code)

    elif types == "float":
        try:
            val = float(val)
            return val
        except ValueError:
            raise KeyError(err_msg, err_code)

    elif types == "string":
        if not isinstance(val, str):
            val = str(val)
        return val

    elif types == "list":
        if not isinstance(val, list):
            raise KeyError(err_msg, err_code)
        return val

    else:
        raise NotImplementedError(f"Type `{types}` not implemented.", err_code)

    # 检查username，password，phone格式的专用函数


def check_require(val, typename):
    if typename == "username":
        if len(val) > MAX_CHAR_LENGTH:
            return False
        if not val.isalnum():  # 只能包含字母和数字
            return False
        return True
    elif typename == "password":
        if len(val) > MAX_CHAR_LENGTH:
            return False
        return True
    elif typename == "email":
        if len(val) > MAX_CHAR_LENGTH:
            return False
        return True
    else:
        return False
