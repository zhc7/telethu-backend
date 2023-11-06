from django.db import models
from users.models import User, GroupList

class Multimedia(models.Model):
    multimedia_id = models.CharField(primary_key=True, max_length=128)  # use the md5 of the file as the id
    multimedia_type = models.IntegerField(blank=False, null=False)  # 0: image, 1: audio, 2: video, 3: file, 4: sticker
    multimedia_user_listener = models.ManyToManyField(User,
                                                      related_name="multimedia_user_listener")  # the user who can see the multimedia
    multimedia_group_listener = models.ManyToManyField(GroupList,
                                                       related_name="multimedia_group_listener")  # the group who can see the multimedia
# Create your models here.
