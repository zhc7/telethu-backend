from django.shortcuts import render
from users.models import MessageList, User
from django.db.models import Q
from utils.data import Message, MessageType

def index(request):
    return render(request, "chat/index.html")


def room(request, room_name):
    return render(request, "chat/room.html", {"room_name": room_name})


def chat_history(request):
    from_value = request.GET.get("from", "")
    num_value = request.GET.get("num", "")
    id_value = request.GET.get("id", "")
    t_type = request.GET.get("t_type", "")
    user_id = request.user_id
    if t_type == 1:
        # group
        messages = MessageList.objects.filter(
            Q(timestamp__lt=from_value), Q(receiver=id_value)
        ).order_by("-timestamp")[:num_value]

    else:
        # user
        messages = MessageList.objects.filter(
            Q(timestamp__lt=from_value),
            (Q(sender=id_value) & Q(receiver=user_id))
            | (Q(receiver=id_value) & Q(sender=user_id)),
        ).order_by("-timestamp")[:num_value]

    messages_list = []
    for msg in messages:
        a = Message(
            message_id=id_value,
            m_type=MessageType.TEXT,
            t_type=t_type,
            time=from_value,
            content=msg.context,
            sender=msg.sender,
            receiver=msg.receiver,
            info=msg.info
        )
        messages_list.append(a)

    return messages_list
    # TODO: 利用上述字段获取数据库中数据
