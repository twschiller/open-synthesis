"""Django Template Authorization Helper Methods.

For more information, please see:
    https://docs.djangoproject.com/en/1.10/howto/custom-template-tags/
"""
from django.template.defaulttags import register

from openach.auth import has_edit_authorization


@register.simple_tag
def can_edit(request, board, has_creator=None):
    """Return True if the request's user has authorization to edit the resource."""
    return has_edit_authorization(request, board, has_creator=has_creator)
