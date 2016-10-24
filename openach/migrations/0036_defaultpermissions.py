"""Initialize default public board permissions."""

from django.conf import settings
from django.db import migrations

from openach.models import AuthLevels


def forwards_func(apps, schema_editor):
    """Create default permissions for each board, if they don't already have permissions."""
    BoardPermissions = apps.get_model("openach", "BoardPermissions")
    Board = apps.get_model("openach", "Board")
    db_alias = schema_editor.connection.alias

    default_read = (
        AuthLevels.registered.key
        if getattr(settings, 'ACCOUNT_REQUIRED', True)
        else AuthLevels.anyone.key
    )

    for board in Board.objects.using(db_alias).all():
        if not BoardPermissions.objects.filter(board=board).exists():
            BoardPermissions.objects.create(
                board=board,
                read_board=default_read,
                read_comments=default_read,
                add_comments=AuthLevels.collaborators.key,
                add_elements=AuthLevels.collaborators.key,
                edit_elements=AuthLevels.collaborators.key
            )


def reverse_func(apps, schema_editor):
    """Do nothing."""
    # we could remove board permissions that currently have default values, but there's no compelling reason to do this
    # at this point.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('openach', '0035_boardpermissions'),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]
