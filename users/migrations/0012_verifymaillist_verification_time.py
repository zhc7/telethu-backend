# Generated by Django 4.2.6 on 2023-12-18 13:04

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0011_loginmaillist"),
    ]

    operations = [
        migrations.AddField(
            model_name="verifymaillist",
            name="verification_time",
            field=models.BigIntegerField(default=0),
        ),
    ]
