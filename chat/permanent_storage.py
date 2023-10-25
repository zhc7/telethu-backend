import pika
from users.models import MessageList


def permanent_storage():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host="localhost"))
    channel = connection.channel()

    channel.exchange_declare(exchange="storage", exchange_type="direct")
    queue_receive = channel.queue_declare(queue="PermStore")

    channel.queue_bind(
        exchange="storage", queue=queue_receive, routing_key="PermStorage"
    )

    def callback(ch, method, properties, body):
        print(f"Received {body} and will be stored!")
        # 将接收到的信息放入数据库
        mes = MessageList(
            message_id=body.message_id,
            m_type=body.m_type,
            t_type=body.t_type,
            time=body.time,
            content=body.content,
            sender=body.sender,
            receiver=body.receiver,
            info=body.info
        )
        mes.save()

    channel.basic_consume(
        queue=queue_receive, on_message_callback=callback, auto_ack=True
    )

    channel.start_consuming()
