# Generated by Django 1.10 on 2016-08-26 16:51

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("openach", "0003_auto_20160825_1622"),
    ]

    operations = [
        migrations.CreateModel(
            name="EvidenceSource",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("source_url", models.URLField()),
                ("submit_date", models.DateTimeField(verbose_name="date added")),
            ],
        ),
        migrations.RemoveField(
            model_name="evidence",
            name="evidence_url",
        ),
        migrations.AddField(
            model_name="evidencesource",
            name="evidence",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="openach.Evidence"
            ),
        ),
        migrations.AddField(
            model_name="evidencesource",
            name="uploader",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
            ),
        ),
    ]
