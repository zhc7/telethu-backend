from functools import wraps
from utils.utils_request import request_failed

MAX_CHAR_LENGTH = 255


# Here err_code == -2 denotes "Error in request body"
# And err_code == -1 denotes "Error in request URL parsing"
def require(body, key, type="string", err_msg=None, err_code=-2):
    if key not in body.keys():
        raise KeyError(err_msg if err_msg is not None
                       else f"Invalid parameters. Expected `{key}`, but not found.", err_code)

    val = body[key]

    err_msg = f"Invalid parameters. Expected `{key}` to be `{type}` type." \
        if err_msg is None else err_msg

    if type == "int":
        try:
            val = int(val)
            return val
        except:
            raise KeyError(err_msg, err_code)

    elif type == "float":
        try:
            val = float(val)
            return val
        except:
            raise KeyError(err_msg, err_code)

    elif type == "string":
        try:
            if not isinstance(val, str):
                raise KeyError(err_msg, err_code)
            val = str(val)
            return val
        except:
            raise KeyError(err_msg, err_code)

    elif type == "list":
        try:
            assert isinstance(val, list)
            return val
        except:
            raise KeyError(err_msg, err_code)

    else:
        raise NotImplementedError(f"Type `{type}` not implemented.", err_code)

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
    elif typename == "phone":
        if len(val) > MAX_CHAR_LENGTH:
            return False
        if not val.isdigit():
            return False
        return True
    else:
        return False


def CheckRequire(check_fn):
    @wraps(check_fn)
    def decorated(*args, **kwargs):
        try:
            return check_fn(*args, **kwargs)
        except Exception as e:
            # Handle exception e
            error_code = -2 if len(e.args) < 2 else e.args[1]
            return request_failed(error_code, e.args[0], 400)  # Refer to below

    return decorated
