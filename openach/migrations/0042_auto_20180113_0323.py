# Generated by Django 1.11.6 on 2018-01-13 03:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("openach", "0041_auto_20180113_0301"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="projectnews",
            options={"verbose_name_plural": "project news"},
        ),
        migrations.AddField(
            model_name="team",
            name="invitation_required",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="team",
            name="public",
            field=models.BooleanField(
                default=True, help_text="Whether or not the team is publicly visible"
            ),
        ),
    ]
