from utils.utils_request import request_failed


class SessionData:
    def __init__(self, request):
        self.request = request

    @property
    def user_id(self):
        return self.request.session.get("user_id")

    @user_id.setter
    def user_id(self, user_id):
        self.request.session["user_id"] = user_id

    @property
    def last_login(self):
        # TODO: 首先判断 user_id 作为 key 的对象是否已经被创建（在首次创建的时候未被初始化，这时就需要手动初始化）
        # print("session is: ", dict(self.request.session.items()))
        user_id_str = str(self.user_id)
        user_info = self.request.session.get(user_id_str)
        print("user_info: ", user_info)
        if not user_info:
            print("no user id! ")
            self.request.session[user_id_str] = {}  # 上面提到的未初始化情况，需要手动初始化
        print("self.user_id: ", self.user_id)
        return self.request.session[user_id_str]["last_login"]

    @last_login.setter
    def last_login(self, last_login):
        user_id_str = str(self.user_id)
        if not self.request.session.get(user_id_str):
            self.request.session[user_id_str] = {}  # 上面提到的未初始化情况，需要手动初始化
        self.request.session[user_id_str]["last_login"] = last_login


class WebSocketSessionData:
    def __init__(self, scope):
        self.scope = scope

    @property
    def user_id(self):
        return self.scope["session"]["user_id"]

    @user_id.setter
    def user_id(self, user_id):
        self.scope["session"]["user_id"] = user_id

    @property
    def last_login(self):
        # TODO: 首先判断 user_id 作为 key 的对象是否已经被创建（在首次创建的时候未被初始化，这时就需要手动初始化）
        print("WS session is: ", self.scope["session"].keys())
        user_id_str = str(self.user_id)
        print("self.user_id is: ", self.user_id)
        print("user_id_str is: ", user_id_str)
        user_info = self.scope["session"][user_id_str]
        print("WS user_info: ", user_info)
        if not user_info:
            print("no WS user id! ")
            self.scope.session[user_id_str] = {}  # 上面提到的未初始化情况，需要手动初始化
        print("WS self.user_id: ", self.user_id)
        return self.scope["session"][user_id_str]["last_login"]

    @last_login.setter
    def last_login(self, last_login):
        user_id_str = str(self.user_id)
        if not self.scope["session"][user_id_str]:
            self.scope["session"][user_id_str] = {}  # 上面提到的未初始化情况，需要手动初始化
        self.scope["session"][user_id_str]["last_login"] = last_login

    @property
    def browser(self):
        return self.scope["session"].get("browser", None)

    @browser.setter
    def browser(self, browser):
        session = self.scope["session"]
        print("session you get is: ", session.keys())
        if not session.get("browser"):
            print("no browser info detected!")
            # 如果浏览器第一次被访问，还没有加入 browser 的相应字段
            self.scope["session"]["browser"] = {}
            self.scope["session"]["browser"] = browser
        else:
            # 表明应该已经不是第一次访问这个浏览器了，那就不用重新设置了
            print("browser existed, browser is ", session.get("browser"))
            pass
