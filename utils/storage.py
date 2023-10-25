import json
import time

import pika

from users.models import MessageList
from utils.data import Message, ContactsData


def storage_callback(ch, method, properties, body):
    print("storing")
    message = Message.model_validate_json(body.decode())
    # 将接收到的信息放入数据库
    mes = MessageList(
        message_id=message.message_id,
        m_type=message.m_type,
        t_type=message.t_type,
        time=message.time,
        content=json.dumps(
            message.content if not isinstance(message.content, ContactsData) else message.content.model_dump()
        ),
        sender=message.sender,
        receiver=message.receiver,
        info=message.info,
    )
    mes.save()
    ch.basic_ack(delivery_tag=method.delivery_tag)
    print("stored")


def start_storage():
    while True:
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host="localhost"))
            break
        except pika.exceptions.AMQPConnectionError:
            print("storage connection failed, retrying...")
            time.sleep(1)
    channel = connection.channel()
    channel.queue_declare(queue="PermStore")
    channel.basic_consume(queue="PermStore", on_message_callback=storage_callback)
    print("storage consumption start")
    channel.start_consuming()
