# Generated by Django 1.10.1 on 2016-09-24 20:39

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("openach", "0025_digeststatus"),
    ]

    operations = [
        migrations.AddField(
            model_name="digeststatus",
            name="last_attempt",
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
