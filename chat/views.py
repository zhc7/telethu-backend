from django.shortcuts import render
from users.models import MessageList, User
from django.db.models import Q
from utils.data import Message, MessageType
from datetime import datetime
from decimal import Decimal  # 用于处理 Decimal 类型的数据
from django.http import HttpRequest, JsonResponse


def index(request):
    print("You are in index")
    return render(request, "chat/index.html")


def room(request, room_name):
    return render(request, "chat/room.html", {"room_name": room_name})


def chat_history(request):
    print("You are getting chat_history!")
    from_value = float(request.GET.get("from", ""))
    print("1")
    num_value = int(request.GET.get("num", ""))
    id_value = int(request.GET.get("id", ""))
    print("id_value is: ", id_value)
    t_type = int(request.GET.get("t_type", ""))
    user_id = int(request.user_id)
    print("user_id is: ", user_id)
    print(id_value)
    print("from value is: ", from_value)
    m = MessageList.objects.filter()
    print("m", m)
    if t_type == 1:
        # group
        messages = MessageList.objects.filter(
            time__gt=float(from_value), receiver=id_value
        ).order_by("-time")[:num_value]

    else:
        print("0!")
        # user
        messages = MessageList.objects.filter(
            Q((Q(sender=id_value) & Q(receiver=user_id)))
            | Q((Q(receiver=id_value) & Q(sender=user_id))),
            time__gt=float(from_value),
        ).order_by("-time")[:num_value]
        print("messages: ", messages)
    messages_list = []
    for msg in messages:
        a = Message(
            message_id=msg.message_id,
            m_type=msg.t_type,
            t_type=msg.t_type,
            time=msg.time,
            content=msg.content,
            sender=msg.sender,
            receiver=msg.receiver,
            info=msg.info,
        )
        messages_list.append(a.model_dump())
    print("ready!")
    print("messages_list: ", messages_list)
    message_list = {"message_you_get": messages_list}
    return JsonResponse(message_list)
    # TODO: 利用上述字段获取数据库中数据
