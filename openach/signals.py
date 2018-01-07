from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Board, BoardPermissions

@receiver(post_save, sender=Board)
def init_board_permissions(sender, **kwargs):
    """Link existing benchmark countries to newly created countries."""
    instance = kwargs['instance']
    if kwargs['created']:
        BoardPermissions.objects.create(board=instance)
