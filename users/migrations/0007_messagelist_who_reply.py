# Generated by Django 4.2.6 on 2023-12-16 06:11

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0006_alter_messagelist_info"),
    ]

    operations = [
        migrations.AddField(
            model_name="messagelist",
            name="who_reply",
            field=models.ManyToManyField(related_name="who_reply", to="users.user"),
        ),
    ]
