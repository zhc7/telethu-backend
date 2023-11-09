# 使用官方的 RabbitMQ 镜像
FROM rabbitmq:3.12-management

# 添加您的应用程序代码、依赖项等

WORKDIR /app


#install redis
RUN apt update
RUN apt install -y lsb-release curl gpg
RUN curl -fsSL https://packages.redis.io/gpg | gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg
RUN echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/redis.list
RUN apt update
RUN apt install -y redis

RUN apt install -y python3-pip

RUN apt install -y libmagic1

COPY requirements.txt .
RUN pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

EXPOSE 80

# 定义容器启动命令
CMD ["/bin/sh", "./start.sh"]