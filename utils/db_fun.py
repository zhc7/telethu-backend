from channels.db import database_sync_to_async
from files.models import Multimedia
from users.models import Friendship, GroupList, User, MessageList
from utils.data import (
    TargetType,
    UserData,
    GroupData,
    FriendType,
)
from utils.uid import globalIdMaker


@database_sync_to_async
def db_query_group_info(group_id_list) -> dict[int, GroupData]:
    group_info = {}
    for group_id in group_id_list:
        group = GroupList.objects.filter(group_id=group_id).first()
        group_date = GroupData(
            id=group.group_id,
            name=group.group_name,
            avatar=group.group_avatar,
            members=[],
            owner=group.group_owner.id,
            admin=[],
            top_message=[],
        )
        for user in group.group_members.all():
            group_date.members.append(user.id)
        for admin in group.group_admin.all():
            group_date.admin.append(admin.id)
        for message in group.group_top_message.all():
            group_date.top_message.append(message.message_id)
        group_info[group_id] = group_date
    return group_info


@database_sync_to_async
def db_query_friends(user_id):
    friends = Friendship.objects.filter(user1=user_id)
    friends = friends | Friendship.objects.filter(user2=user_id)
    friends_id = []
    for friend in friends:
        if friend.state == 1:
            if str(friend.user1.id) == str(user_id):
                friend_id = friend.user2.id
            else:
                friend_id = friend.user1.id
            if friend_id not in friends_id:
                friends_id.append(friend_id)
    return friends_id


@database_sync_to_async
def db_query_friends_info(friends_id) -> dict[int, UserData]:
    friends_info = {}
    for friend_id in friends_id:
        friend = User.objects.filter(id=friend_id).first()
        friend_info = UserData(
            id=friend.id,
            name=friend.username,
            avatar=friend.avatar,
            email=friend.userEmail,
        )
        friends_info[friend_id] = friend_info
    return friends_info


@database_sync_to_async
def db_query_group(self_user_id):
    # 这个方法执行同步数据库查询
    groups = GroupList.objects.filter(group_members=self_user_id)
    group_id = []
    group_names = {}
    group_members = {}
    group_owner = {}
    group_admin = {}
    for group in groups:
        group_id.append(int(group.group_id))
        group_members_user = group.group_members.all()
        group_members_id = []
        for user in group_members_user:
            group_members_id.append(int(user.id))
        group_members[group.group_id] = group_members_id
        group_names[group.group_id] = group.group_name
        if group.group_owner is not None:
            group_owner[group.group_id] = group.group_owner.id
        group_admin[group.group_id] = []
        for admin in group.group_admin.all():
            group_admin[group.group_id].append(admin.id)
    return group_id, group_members, group_names, group_owner, group_admin


@database_sync_to_async
def db_build_group(friend_list, user_id, group_name, group_members):
    user = User.objects.filter(id=user_id).first()
    group = GroupList.objects.create(
        group_id=globalIdMaker.get_id(), group_name=group_name, group_owner=user
    )
    for member in group_members:
        if member in friend_list or member == user_id:
            group.group_members.add(member)
    group.save()
    id_list = []
    for member in group.group_members.all():
        id_list.append(member.id)
    return group, id_list


@database_sync_to_async
def db_add_member(self_user_id, self_friend_list, group_id, add_member):
    group = GroupList.objects.filter(group_id=group_id).first()
    if group is None:
        print("group not exist")
        return None, None
    # 判断自己是否在群里，不在就加不了人
    user = User.objects.filter(id=self_user_id).first()
    if user not in group.group_members.all():
        print("user not in group")
        return None, None
    # 判断被加的是否是好友
    for member in add_member:
        if member in self_friend_list:
            group.group_members.add(member)
    group.save()
    id_list = []
    for member in group.group_members.all():
        id_list.append(member.id)
    return group, id_list


@database_sync_to_async
def db_change_group_owner(group_id, old_owner, new_owner):
    group = GroupList.objects.filter(group_id=group_id).first()
    if group is None:
        raise KeyError("group not exist")
    if group.group_owner is None:
        raise KeyError("group owner not exist,this group must be deleted")
    if group.group_owner.id != old_owner:
        raise KeyError("you are not the owner")
    user = User.objects.filter(id=new_owner).first()
    if user is None:
        raise KeyError("new owner not exist")
    if user not in group.group_members.all():
        raise KeyError("new owner not in group")
    group.group_owner = user
    group.save()
    return group.group_id


@database_sync_to_async
def db_from_id_to_meta(id_list):
    users_info = []
    for user_id in id_list:
        user = User.objects.filter(id=user_id).first()
        user_info = UserData(
            id=user.id,
            name=user.username,
            avatar=user.avatar,
            email=user.userEmail,
        )
        users_info.append(user_info)
    return users_info


@database_sync_to_async
def db_friendship(user_id, friend_id):
    friendship = None
    # 排除自我添加
    if user_id == friend_id:
        return FriendType.user_equal_friend
    user = User.objects.filter(id=user_id).first()
    friend = User.objects.filter(id=friend_id).first()
    if friend is None:
        return FriendType.friend_not_exist, "friend_not_exist"
    # 检查是否已经是好友
    if user.user1_friendships.filter(user2=friend).exists():
        friendship = user.user1_friendships.get(user2=friend)
    elif user.user2_friendships.filter(user1=friend).exists():
        friendship = user.user2_friendships.get(user1=friend)
    if friendship is not None:
        if friendship.state == 1:
            return FriendType.already_friend, "already_friend"
        elif friendship.state == 0 and friendship.user1 == user:
            return FriendType.already_send_apply, "already_send_apply"
        elif friendship.state == 0 and friendship.user2 == user:
            return FriendType.already_receive_apply, "already_receive_apply"
        elif friendship.state == 2 and friendship.user1 == user:
            return FriendType.already_block_friend, "already_block_friend"
        elif friendship.state == 2 and friendship.user2 == user:
            return FriendType.already_been_block, "already_been_block"
        elif friendship.state == 3 and friendship.user1 == user:
            return FriendType.already_reject_friend, "already_reject_friend"
        elif friendship.state == 3 and friendship.user2 == user:
            return FriendType.already_been_reject, "already_been_reject"
    else:
        return FriendType.relationship_not_exist, "relationship_not_exist"


@database_sync_to_async
def db_friendship_change(user_id, friend_id, state):
    friendship = None
    # 排除自我添加
    if user_id == friend_id:
        return FriendType.user_equal_friend
    user = User.objects.filter(id=user_id).first()
    friend = User.objects.filter(id=friend_id).first()
    # 检查是否已经是好友
    if user.user1_friendships.filter(user2=friend).exists():
        friendship = user.user1_friendships.get(user2=friend)
    elif user.user2_friendships.filter(user1=friend).exists():
        friendship = user.user2_friendships.get(user1=friend)
    if friendship is not None:
        friendship.state = state
        friendship.user1 = user
        friendship.user2 = friend
        friendship.save()
        return True
    else:
        friendship = Friendship.objects.create(user1=user, user2=friend, state=state)
        friendship.save()
        return True


@database_sync_to_async
def db_create_multimedia(self_user_id, m_type, md5, t_type, user_or_group):
    if t_type == TargetType.FRIEND:  # IF FRIEND
        # if exist
        if Multimedia.objects.filter(multimedia_id=md5).exists():
            Multimedia.objects.filter(
                multimedia_id=md5
            ).first().multimedia_user_listener.add(user_or_group)
            Multimedia.objects.filter(
                multimedia_id=md5
            ).first().multimedia_user_listener.add(self_user_id)
        else:
            multimedia = Multimedia.objects.create(
                multimedia_id=md5, multimedia_type=m_type
            )
            multimedia.multimedia_user_listener.add(user_or_group)
            multimedia.multimedia_user_listener.add(self_user_id)
            multimedia.save()
    elif t_type == TargetType.GROUP:  # IF GROUP
        if Multimedia.objects.filter(multimedia_id=md5).exists():
            Multimedia.objects.filter(
                multimedia_id=md5
            ).first().multimedia_group_listener.add(user_or_group)
        else:
            multimedia = Multimedia.objects.create(
                multimedia_id=md5, multimedia_type=m_type
            )
            multimedia.multimedia_group_listener.add(user_or_group)
            multimedia.save()
    return


@database_sync_to_async
def db_add_or_remove_admin(group_id, admin_id, user_id, if_add):
    group = GroupList.objects.filter(group_id=group_id).first()
    if group is None:
        raise KeyError("group not exist")
    if group.group_owner is None:
        raise KeyError("group owner not exist,this group must be deleted")
    if group.group_owner.id != user_id:
        raise KeyError("you are not the owner")
    if group.group_owner.id == admin_id:
        raise KeyError("you are the owner")
    user = User.objects.filter(id=admin_id).first()
    if user is None:
        raise KeyError("new admin not exist")
    if user not in group.group_members.all():
        raise KeyError("new admin not in group")
    if if_add:
        if user in group.group_admin.all():
            raise KeyError("already admin")
        group.group_admin.add(user)
    else:
        if user not in group.group_admin.all():
            raise KeyError("not admin")
        group.group_admin.remove(user)
    group.save()
    return True


@database_sync_to_async
def db_group_remove_member(group_id, remove_id, user_id):
    group = GroupList.objects.filter(group_id=group_id).first()
    if group is None:
        raise KeyError("group not exist")
    if group.group_owner is None:
        raise KeyError("group owner not exist,this group must be deleted")
    if group.group_owner.id != user_id and user_id not in group.group_admin.all():
        raise KeyError("you are not the owner or admin")
    user = User.objects.filter(id=remove_id).first()
    if user is None:
        raise KeyError("remove user not exist")
    if user not in group.group_members.all():
        raise KeyError("remove user not in group")
    if user == group.group_owner:
        raise KeyError("you cannot remove owner")
    if user in group.group_admin.all() and user_id != group.group_owner.id:
        raise KeyError("you cannot remove admin if you are not owner")
    group.group_members.remove(user)
    if user in group.group_admin.all():
        group.group_admin.remove(user)
    group.save()
    return True


@database_sync_to_async
def db_add_or_del_top_message(group_id, message_id, user_id, if_add):
    group = GroupList.objects.filter(group_id=group_id).first()
    if group is None:
        raise KeyError("group you chose not exist")
    if group.group_owner is None:
        raise KeyError("group owner not exist,this group must be deleted")
    if group.group_owner.id != user_id and user_id not in group.group_admin.all():
        raise KeyError("you are not the owner or admin")
    message = MessageList.objects.filter(message_id=message_id).first()
    if message is None:
        raise KeyError("message not exist")
    if message.receiver != group_id:
        raise KeyError("message not in group")
    if if_add:
        if message in group.group_top_message.all():
            raise KeyError("message already top")
        group.group_top_message.add(message)
    else:
        if message not in group.group_top_message.all():
            raise KeyError("message not top")
        group.group_top_message.remove(message)
    group.save()
    return True


@database_sync_to_async
def db_add_read_message(self_group_list, message_id, user_id):
    message = MessageList.objects.filter(message_id=message_id).first()
    if message is None:
        return "no such message", None, None
    print(message.receiver, user_id, self_group_list)
    if message.receiver != user_id and message.receiver not in self_group_list:
        return "you cannot read this message", None, None
    else:
        message.who_read.add(user_id)
        message.save()
        return message.sender, message.receiver, message.t_type


@database_sync_to_async
def db_reduce_person(group_id, person_id):
    group = GroupList.objects.filter(group_id=group_id).first()
    if group is None:
        return None
    group.group_members.remove(person_id)
    group.save()
    return group.group_id
