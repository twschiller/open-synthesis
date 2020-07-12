import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_safe
from notifications.signals import notify

from .util import make_paginator

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


@require_safe
@login_required
def notifications(request):
    """Return a paginated list of notifications for the user."""
    notification_list = request.user.notifications.unread()
    context = {
        "notifications": make_paginator(request, notification_list),
    }
    return render(request, "boards/notifications/notifications.html", context)


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def clear_notifications(request):
    """Handle POST request to clear notifications and redirect user to their profile."""
    if request.method == "POST":
        if "clear" in request.POST:
            request.user.notifications.mark_all_as_read()
            messages.success(request, _("Cleared all notifications."))
    return HttpResponseRedirect("/accounts/profile")


def notify_followers(board, actor, verb, action_object):
    """Notify board followers of that have read permissions for the board."""
    for follow in board.followers.all().select_related("user"):
        if follow.user != actor and board.can_read(follow.user):
            notify.send(
                actor,
                recipient=follow.user,
                actor=actor,
                verb=verb,
                action_object=action_object,
                target=board,
            )


def notify_add(board, actor, action_object):
    """Notify board followers of an addition."""
    notify_followers(board, actor, "added", action_object)


def notify_edit(board, actor, action_object):
    """Notify board followers of an edit."""
    notify_followers(board, actor, "edited", action_object)
