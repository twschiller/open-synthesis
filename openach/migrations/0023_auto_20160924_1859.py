# Generated by Django 1.10.1 on 2016-09-24 18:59

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("openach", "0022_auto_20160924_1845"),
    ]

    operations = [
        migrations.AlterField(
            model_name="usersettings",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to=settings.AUTH_USER_MODEL,
                unique=True,
            ),
        ),
    ]
