import json

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from utils.data import MessageStatusType
from users.models import MessageList
from utils.data import Message
from utils.session import SessionData
from utils.utils_request import request_failed, request_success, BAD_METHOD
from django.views.decorators.csrf import csrf_exempt

def index(request):
    print("You are in index")
    return render(request, "chat/index.html")


def room(request, room_name):
    return render(request, "chat/room.html", {"room_name": room_name})


def chat_history(request):
    print("You're getting chat history!")
    # Parameters
    from_value = int(request.GET.get("from", 0)) # Get all the message from this time 
    num_value = int(request.GET.get("num", -1)) # Number of messages we ought to get, default to be -1 to show no limits
    id_value = int(request.GET.get("id", "")) # id_value stands for the user that receives the message
    t_type = int(request.GET.get("t_type", ""))
    user_id = int(request.user_id)
    print("user_id is: ", user_id)
    if t_type == 1:
        # group
        # we should exclude the message recalled as well as the message deleted by the receiver
        messages = MessageList.objects.filter(
            ~Q(deleted_users__in=[user_id]),
            time__lt=from_value, receiver=id_value, t_type=t_type 
        ).order_by("-time")[:num_value]

    else:
        print("0!")
        # user
        # we should exclude the message recalled as well as the message deleted by the receiver
        messages = MessageList.objects.filter(
            Q((Q(sender=id_value) & Q(receiver=user_id)))
            | Q((Q(receiver=id_value) & Q(sender=user_id))),
            ~Q(deleted_users__in=[user_id]),
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
        if msg.status == MessageStatusType.RECALLED:
            a.content = "This message has been recalled! "
        messages_list.append(a.model_dump())
    messages_list.reverse()
    print("ready!")
    print("messages_list: ", messages_list)
    return JsonResponse(messages_list, safe=False)
    # TODO: 利用上述字段获取数据库中数据
    
def filter_history():
    pass