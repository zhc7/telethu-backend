import json

from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from users.models import MessageList, GroupList, User, Friendship
from utils.data import Message, TargetType
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
        who_reply=[message.message_id for message in msg.who_reply.all()],
        status=msg.status
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
    return messages_list

@csrf_exempt
def chat_history(request):
    print("You're getting chat history!")
    # Parameters
    from_value = int(request.GET.get("from", 0))  # Get all the message from this time
    to_value = int(request.GET.get("to", 0))
    alignment = request.GET.get("alignment", "from")
    num_value = int(
        request.GET.get("num", -1)
    )  # Number of messages we ought to get, default to be -1 to show no limits
    id_value = int(
        request.GET.get("id", "")
    )  # id_value stands for the user that receives the message
    t_type = int(request.GET.get("t_type", ""))
    user_id = int(request.user_id)

    if t_type == TargetType.GROUP:
        # group
        # we should exclude the message recalled as well as the message deleted by the receiver
        messages = MessageList.objects.filter(
            ~Q(deleted_users__in=[user_id]),
            time__lt=from_value,
            time__gt=to_value,
            receiver=id_value,
            t_type=t_type,
        ).order_by("-time" if alignment == "from" else "time")[:num_value]

    else:
        # user
        # we should exclude the message recalled as well as the message deleted by the receiver
        messages = MessageList.objects.filter(
            Q((Q(sender=id_value) & Q(receiver=user_id)))
            | Q((Q(receiver=id_value) & Q(sender=user_id))),
            ~Q(deleted_users__in=[user_id]),
            time__lt=from_value,
            time__gt=to_value,
            t_type=t_type,
        ).order_by("-time" if alignment == "from" else "time")[:num_value]

    message_filtered = []
    for m in messages:
        if m.status & MessageStatusType.RECALLED:
            m.content = json.dumps("This message has been recalled!")
        message_filtered.append(m)
    messages_list = load_message_from_list(message_filtered)
    if alignment == "from":
        messages_list.reverse()

    print("messages_list: ", messages_list)
    return JsonResponse(messages_list, safe=False)


@csrf_exempt
def filter_history(request):
    print("You are filtering history! ")
    from_value = int(request.GET.get("from", 0))  # Get all the message from this time
    to_value = int(
        request.GET.get("to", -1)
    )  # Get all the message before this time, default to be -1 to show no limits
    id_value = int(
        request.GET.get("id", -1)
    )  # id_value stands for the user that receives the message
    m_type = int(request.GET.get("m_type", -1))  # m_type
    content = str(
        request.GET.get("content", "")
    )  # The content of the message, user __contain
    num_value = int(
        request.GET.get("num", 100)
    )  # Number of messages we ought to get, default to be -1 to show no limits
    user_id = int(request.user_id)
    # First, find all the message within from_value and to value
    if id_value == -1:
        id_value = user_id
    # Note that id_value stands for the receiver for search, therefore the user has a risk of searching other's
    # chat history.
    user = User.objects.filter(id=user_id).first()
    in_group = GroupList.objects.filter(group_id=id_value).first()

    if in_group is None:
        # id stands for user
        print("id_value: ", id_value)
        print("user_id", user_id)
        if not (Friendship.objects.filter(user1=id_value, user2=user_id).exists() or Friendship.objects.filter(
            user2=user_id, user1=id_value).exists()):
            return request_failed(code=403, info="can't view other's chat history!")
    else:
        is_member = user in in_group.group_members.all()
        if not is_member:
            return request_failed(code=403, info="can't view chat history in a group that you are not in!")
    
    to_time = Q()
    if to_value != -1:
        to_time = Q(time__lt=to_value)
    
    group_ = Q(receiver = id_value)
    if not in_group:
        group_ = (Q(receiver = id_value) & Q(sender = user_id)) | (Q(receiver = user_id) & Q(sender = id_value))
    query = ~Q(deleted_users__in=[user_id]) & group_ & Q(time__gt=from_value) & Q(m_type=m_type)
    if content != "":
        query = query & Q(content__icontains=content)
    if to_value != -1:
        print("no to!")
        query = query & to_time
    
    messages = []
            
    messages_unrecalled = MessageList.objects.filter(
            query
        ).order_by("-time")[:num_value]
    
    print("messages unrecalled: ", messages_unrecalled)
    for m in messages_unrecalled:
        if not (m.status & MessageStatusType.RECALLED):
            messages.append(m)


    messages_list = load_message_from_list(messages)
    messages_list.reverse()

    print("messages_list: ", messages_list)
    return JsonResponse(messages_list, safe=False)


def get_message(request, message_id):
    user_id=request.user_id
    if user_id is None:
        return request_failed(code=403, info="User id is not provided! ")
    user = User.objects.filter(id=user_id).first()
    if user is None:
        return request_failed(code=403, info="User not found! ")
    if request.method != "GET":
        return BAD_METHOD
    if message_id is None:
        return request_failed(code=403, info="Message id is not provided! ")
    message = MessageList.objects.filter(message_id=message_id).first()
    if message is None:
        return request_failed(code=403, info="Message not found! ")
    if message.sender != user_id:
        if message.receiver != user_id:
            group = GroupList.objects.filter(group_id=message.receiver).first()
            if group is None or user not in group.group_members.all():
                return request_failed(code=403, info="You are not the sender or receiver of this message! ")
    message_response = load_message(message)
    return request_success(message_response.model_dump())
