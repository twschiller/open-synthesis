"""Migration to initialize default UserSettings for each user."""

from django.db import migrations


def forwards_func(apps, schema_editor):
    """Create default UserSettings for each user, if they don't already have settings."""
    User = apps.get_model("auth", "User")
    UserSettings = apps.get_model("openach", "UserSettings")
    db_alias = schema_editor.connection.alias

    # doesn't matter that this is inefficient because we don't have many users yet
    for user in User.objects.using(db_alias).all():
        UserSettings.objects.update_or_create(user=user)


def reverse_func(apps, schema_editor):
    """Remove all UserSettings."""
    UserSettings = apps.get_model("openach", "UserSettings")
    db_alias = schema_editor.connection.alias
    UserSettings.objects.using(db_alias).all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("openach", "0027_auto_20160924_2043"),
        ("auth", "0008_alter_user_username_max_length"),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]
