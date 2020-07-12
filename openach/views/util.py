from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext as _

def remove_and_redirect(request, removable, message_detail):
    """Mark a model as removed and redirect the user to the associated board detail page."""
    if getattr(settings, 'EDIT_REMOVE_ENABLED', True):
        removable.removed = True
        removable.save()
        class_name = removable._meta.verbose_name.title()  # pylint: disable=protected-access
        class_ = class_name[:1].lower() + class_name[1:] if class_name else ''
        messages.success(request, _('Removed {object_type}: {detail}').format(object_type=class_, detail=message_detail))  # nopep8
        return HttpResponseRedirect(reverse('openach:detail', args=(removable.board.id,)))
    else:
        raise PermissionDenied()


def make_paginator(request, object_list, per_page=10, orphans=3):
    """Return a paginator for object_list from request."""
    paginator = Paginator(object_list, per_page=per_page, orphans=orphans)
    page = request.GET.get('page')
    try:
        objects = paginator.page(page)
    except PageNotAnInteger:
        # if page is not an integer, deliver first page.
        objects = paginator.page(1)
    except EmptyPage:
        # if page is out of range (e.g. 9999), deliver last page of results.
        objects = paginator.page(paginator.num_pages)
    return objects
