# Generated by Django 4.2.6 on 2023-12-09 03:27

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0005_grouplist_group_admin_grouplist_group_owner_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="messagelist",
            name="info",
            field=models.CharField(blank=True, default="", max_length=256, null=True),
        ),
    ]
