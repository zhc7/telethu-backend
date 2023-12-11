import json

from django.db.models import Q, F
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from users.models import MessageList, GroupList, User
from utils.data import Message
from utils.data import MessageStatusType
from utils.utils_request import request_failed, request_success, BAD_METHOD


def load_message(msg):
    try:
        info = json.loads(msg.info)
    except json.decoder.JSONDecodeError:
        info = msg.info
    loaded_message = Message(
        message_id=msg.message_id,
        m_type=msg.m_type,
        t_type=msg.t_type,
        time=msg.time,
        content=json.loads(msg.content),
        sender=msg.sender,
        receiver=msg.receiver,
        info=info,
        who_read=[user.id for user in msg.who_read.all()],
    )
    if loaded_message.status and loaded_message.status & MessageStatusType.RECALLED:
        loaded_message.content = "This message has been recalled! "
    return loaded_message


def load_message_from_list(msg_list):
    messages_list = []
    for msg in msg_list:
        print("msg.content: ", msg.content)
        loaded_message = load_message(msg)
        messages_list.append(loaded_message.model_dump())
    messages_list.reverse()
    return messages_list


def chat_history(request):
    print("You're getting chat history!")
    # Parameters
    from_value = int(request.GET.get("from", 0))  # Get all the message from this time
    num_value = int(
        request.GET.get("num", -1)
    )  # Number of messages we ought to get, default to be -1 to show no limits
    id_value = int(
        request.GET.get("id", "")
    )  # id_value stands for the user that receives the message
    t_type = int(request.GET.get("t_type", ""))
    user_id = int(request.user_id)
    print("user_id is: ", user_id)
    messages = []
    if t_type == 1:
        # group
        # we should exclude the message recalled as well as the message deleted by the receiver
        messages = MessageList.objects.filter(
            ~Q(deleted_users__in=[user_id]),
            time__lt=from_value,
            receiver=id_value,
            t_type=t_type,
        ).order_by("-time")[:num_value]

    else:
        # user
        # we should exclude the message recalled as well as the message deleted by the receiver
        messages = MessageList.objects.filter(
            Q((Q(sender=id_value) & Q(receiver=user_id)))
            | Q((Q(receiver=id_value) & Q(sender=user_id))),
            ~Q(deleted_users__in=[user_id]),
            time__lt=from_value,
            t_type=t_type,
        ).order_by("-time")[:num_value]
        #print("messages: ", messages)
    
    message_recalled = []
    for m in messages:
        if (m.status & MessageStatusType.RECALLED):
            m.content = json.dumps("This message has been recalled!")
        message_recalled.append(m)
    messages_list = load_message_from_list(message_recalled)
    print("ready!")
    print("messages_list: ", messages_list)
    return JsonResponse(messages_list, safe=False)
    # TODO: 利用上述字段获取数据库中数据


@csrf_exempt
def filter_history(request):
    print("You are filtering history! ")
    from_value = int(request.GET.get("from", 0))  # Get all the message from this time
    to_value = int(
        request.GET.get("to", -1)
    )  # Get all the message before this time, default to be -1 to show no limits
    m_type = int(request.GET.get("m_type", -1))  # m_type
    sender = int(request.GET.get("sender", -1))  # The id of sender
    content = str(
        request.GET.get("content", "")
    )  # The content of the message, user __contain
    num_value = int(
        request.GET.get("num", 100)
    )  # Number of messages we ought to get, default to be -1 to show no limits
    user_id = int(request.user_id)
    # First, find all the message within from_value and to value
    if content != "":
        print("content! ")
        messages_unrecalled = MessageList.objects.filter(
            ~Q(deleted_users__in=[user_id]),
            content__icontains=content,
            time__gt=from_value,
        ).order_by("-time")[:num_value]
        messages = []
        for m in messages_unrecalled:
            if (m.status & MessageStatusType.RECALLED):
                m.content = json.dumps("This message has been recalled!")
            messages.append(m)
    else:
        messages_unrecalled = MessageList.objects.filter(
            ~Q(deleted_users__in=[user_id]),
            time__gt=from_value,
        ).order_by("-time")[:num_value]
        messages = []
        for m in messages_unrecalled:
            if (m.status & MessageStatusType.RECALLED):
                m.content = json.dumps("This message has been recalled!")
            messages.append(m)

    # You may get some message that you shouldn't receive
    f_messages = []
    user = User.objects.filter(id=user_id).first()

    # Preprocessing
    for message in messages:
        if message.m_type < 6:
            if message.t_type == 0:
                if message.sender == user_id or message.receiver == user_id:
                    f_messages.append(message)
            elif message.t_type == 1:
                group = GroupList.objects.filter(group_id=message.receiver).first()
                if group is not None:
                    is_member = user in group.group_members.all()
                    if is_member:
                        f_messages.append(message)

    messages = f_messages

    # If to_value != -1, then filter the messages to get all that's sent earlier than to_value
    if to_value != -1:
        f_messages = [message for message in messages if message.time < to_value]
        messages = f_messages

    # if m_type != -1, then filter all the messages with m_type
    if m_type != -1:
        f_messages = [message for message in messages if message.m_type == m_type]
        messages = f_messages

    # if sender != -1, then filter all the message sent by sender
    if sender != -1:
        f_messages = [message for message in messages if message.sender == sender]
        messages = f_messages

    messages_list = load_message_from_list(messages)

    print("messages_list: ", messages_list)
    return JsonResponse(messages_list, safe=False)


def get_message(request, message_id):
    if request.method != "GET":
        return BAD_METHOD
    if message_id is None:
        return request_failed(code=403, info="Message id is not provided! ")
    message = MessageList.objects.filter(message_id=message_id).first()
    if message is None:
        return request_failed(code=403, info="Message not found! ")
    message_response = load_message(message)
    return request_success(message_response.model_dump())
