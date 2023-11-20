import json

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from utils.data import MessageStatusType
from users.models import MessageList
from utils.data import Message
from utils.utils_request import request_failed, request_success


def index(request):
    print("You are in index")
    return render(request, "chat/index.html")


def room(request, room_name):
    return render(request, "chat/room.html", {"room_name": room_name})


def chat_history(request):
    print("You are getting chat_history!")
    from_value = int(request.GET.get("from", ""))
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
            time__lt=from_value, receiver=id_value, t_type=t_type
        ).order_by("-time")[:num_value]

    else:
        print("0!")
        # user
        messages = MessageList.objects.filter(
            Q((Q(sender=id_value) & Q(receiver=user_id)))
            | Q((Q(receiver=id_value) & Q(sender=user_id))),
            time__lt=from_value,
            t_type=t_type,
        ).order_by("-time")[:num_value]
        print("messages: ", messages)
    messages_list = []
    for msg in messages:
        print("msg.content: ", msg.content)
        a = Message(
            message_id=msg.message_id,
            m_type=msg.m_type,
            t_type=msg.t_type,
            time=msg.time,
            content=json.loads(msg.content),
            sender=msg.sender,
            receiver=msg.receiver,
            info=msg.info,
        )
        messages_list.append(a.model_dump())
    messages_list.reverse()
    print("ready!")
    print("messages_list: ", messages_list)
    return JsonResponse(messages_list, safe=False)
    # TODO: 利用上述字段获取数据库中数据


def recall(request, message_id):
    m = MessageList.objects.get(message_id=message_id)
    if m is None:
        return request_failed(
            2, "Can't recall a message that doesn't exist! ", status_code=401
        )
    else:
        pass
        # Execute a rather complicated logic


def delete(request, message_id):
    m = MessageList.objects.get(message_id=message_id)
    if m is None:
        return request_failed(
            2, "Can't delete a message that doesn't exist! ", status_code=401
        )
    else:
        m.status = MessageStatusType.DELETED
        m.save()
        return request_success()
