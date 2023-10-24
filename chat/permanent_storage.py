from consumers import Message


async def perm_store(message_received: Message):
    channel = await rabbitmq_connection.channel()
    queue_permanent_storage = await channel.declare_queue("queue_permanent_storage")
