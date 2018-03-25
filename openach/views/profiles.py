import logging

from django.conf import  settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, get_object_or_404
from django.utils.translation import ugettext as _
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods, require_safe

from openach.decorators import account_required
from openach.forms import SettingsForm
from openach.metrics import user_boards_contributed, user_boards_created, user_boards_evaluated

PAGE_CACHE_TIMEOUT_SECONDS = getattr(settings, 'PAGE_CACHE_TIMEOUT_SECONDS', 60)

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


@require_http_methods(['HEAD', 'GET', 'POST'])
@login_required
def private_profile(request):
    """Return a view of the private profile associated with the authenticated user and handle settings."""
    user = request.user

    if request.method == 'POST':
        form = SettingsForm(request.POST, instance=user.settings)
        if form.is_valid():
            form.save()
            messages.success(request, _('Updated account settings.'))
    else:
        form = SettingsForm(instance=user.settings)

    context = {
        'user': user,
        'boards_created': user_boards_created(user, viewing_user=user)[:5],
        'boards_contributed': user_boards_contributed(user, viewing_user=user),
        'board_voted': user_boards_evaluated(user, viewing_user=user),
        'meta_description': _('Account profile for user {name}').format(name=user),
        'notifications': request.user.notifications.unread(),
        'settings_form': form,
    }
    return render(request, 'boards/profile.html', context)


@require_safe
@cache_page(PAGE_CACHE_TIMEOUT_SECONDS)
def public_profile(request, account_id):
    """Return a view of the public profile associated with account_id."""
    user = get_object_or_404(User, pk=account_id)
    context = {
        'user': user,
        'boards_created': user_boards_created(user, viewing_user=request.user)[:5],
        'boards_contributed': user_boards_contributed(user, viewing_user=request.user),
        'board_voted': user_boards_evaluated(user, viewing_user=request.user),
        'meta_description': _('Account profile for user {name}').format(name=user),
    }
    return render(request, 'boards/public_profile.html', context)


@require_http_methods(['HEAD', 'GET', 'POST'])
@account_required
def profile(request, account_id):
    """Return a view of the profile associated with account_id.

    If account_id corresponds to the authenticated user, return the private profile view. Otherwise return the public
    profile.
    """
    return private_profile(request) if request.user.id == int(account_id) else public_profile(request, account_id)

