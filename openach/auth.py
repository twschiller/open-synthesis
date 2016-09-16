"""Analysis of Competing Hypotheses Authorization Functions."""
from django.conf import settings
from django.core.exceptions import PermissionDenied


def has_edit_authorization(request, board, has_creator=None):
    """Return True if the user does not have edit rights for the resource.

    :param request: a Django request object
    :param board: the Board context
    :param has_creator: a model that has a creator member, or None
    """
    return request.user.is_authenticated() and (
        getattr(settings, 'EDIT_AUTH_ANY', False) or owner_or_staff(request, board, has_creator)
    )


def check_edit_authorization(request, board, has_creator=None):
    """Raise a PermissionDenied exception if the user does not have edit rights for the resource.

    :param request: a Django request object
    :param board: the Board context
    :param has_creator: a model that has a creator member, or None
    """
    if has_edit_authorization(request, board, has_creator=has_creator):
        pass
    else:
        raise PermissionDenied()


def owner_or_staff(request, board, has_creator=None):
    """Return True if the user is authenticated and has ownership of the resource.

    :param request: a Django request object
    :param board: the Board context
    :param has_creator: a model that has a creator member, or None
    """
    return request.user.is_staff or \
        request.user.id == board.creator_id or \
        (has_creator and request.user.id == has_creator.creator_id)
