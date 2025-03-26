"""Analysis of Competing Hypotheses Authorization Functions."""

from django.core.exceptions import PermissionDenied


def has_edit_authorization(request, board, has_creator=None):
    """Return True if the user does not have edit rights for the resource.

    :param request: a Django request object
    :param board: the Board context
    :param has_creator: a model that has a creator member, or None
    """
    permissions = board.permissions.for_user(request.user)
    return "edit_elements" in permissions or (
        has_creator and request.user.id == has_creator.creator_id
    )


def check_edit_authorization(request, board, has_creator=None):
    """Raise a PermissionDenied exception if the user does not have edit rights for the resource.

    :param request: a Django request object
    :param board: the Board context
    :param has_creator: a model that has a creator member, or None
    """
    if not has_edit_authorization(request, board, has_creator=has_creator):
        raise PermissionDenied()
