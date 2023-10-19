class SessionData:
    def __init__(self, request):
        self.request = request

    @property
    def user_email(self):
        return self.request.session.get("user_email")

    @user_email.setter
    def user_email(self, user_email):
        self.request.session["user_email"] = user_email

    @property
    def last_login(self):
        # TODO: 首先判断 username 作为 key 的对象是否已经被创建（在首次创建的时候未被初始化，这时就需要手动初始化）
        if not self.request.session.get(self.user_email):
            self.request.session[self.user_email] = {}  # 上面提到的未初始化情况，需要手动初始化
        return self.request.session[self.user_email]["last_login"]

    @last_login.setter
    def last_login(self, last_login):
        if not self.request.session.get(self.user_email):
            self.request.session[self.user_email] = {}  # 上面提到的未初始化情况，需要手动初始化
        self.request.session[self.user_email]["last_login"] = last_login

    # TODO: 需要建立的数据结构：将 username 作为 key; last_login 作为 value 的一个字段 （实际上 value 应该是一个 struct）
