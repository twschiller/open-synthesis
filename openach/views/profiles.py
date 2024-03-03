import logging

from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods, require_safe
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site
from notifications.signals import notify

from openach.forms import IssueInviteForm
from openach.models import Invitation

from openach.decorators import account_required
from openach.forms import SettingsForm
from openach.metrics import (
    user_boards_contributed,
    user_boards_created,
    user_boards_evaluated,
)

PAGE_CACHE_TIMEOUT_SECONDS = getattr(settings, "PAGE_CACHE_TIMEOUT_SECONDS", 60)

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


@require_http_methods(["HEAD", "GET", "POST"])
@login_required
def private_profile(request):
    """Return a view of the private profile associated with the authenticated user and handle settings."""
    user = request.user

    if request.method == "POST":
        form = SettingsForm(request.POST, instance=user.settings)
        if form.is_valid():
            form.save()
            messages.success(request, _("Updated account settings."))
    else:
        form = SettingsForm(instance=user.settings)

    context = {
        "user": user,
        "boards_created": user_boards_created(user, viewing_user=user)[:5],
        "boards_contributed": user_boards_contributed(user, viewing_user=user),
        "board_voted": user_boards_evaluated(user, viewing_user=user),
        "meta_description": _("Account profile for user {name}").format(name=user),
        "notifications": request.user.notifications.unread(),
        "settings_form": form,
    }
    return render(request, "boards/profile.html", context)


@require_safe
@cache_page(PAGE_CACHE_TIMEOUT_SECONDS)
def public_profile(request, account_id):
    """Return a view of the public profile associated with account_id."""
    user = get_object_or_404(User, pk=account_id)
    context = {
        "user": user,
        "boards_created": user_boards_created(user, viewing_user=request.user)[:5],
        "boards_contributed": user_boards_contributed(user, viewing_user=request.user),
        "board_voted": user_boards_evaluated(user, viewing_user=request.user),
        "meta_description": _("Account profile for user {name}").format(name=user),
    }
    return render(request, "boards/public_profile.html", context)


@require_http_methods(["HEAD", "GET", "POST"])
@account_required
def profile(request, account_id):
    """Return a view of the profile associated with account_id.

    If account_id corresponds to the authenticated user, return the private profile view. Otherwise return the public
    profile.
    """
    return (
        private_profile(request)
        if request.user.id == int(account_id)
        else public_profile(request, account_id)
    )




@login_required
@require_http_methods(["POST"])
@transaction.atomic
def issue_invite(request):
    if request.user.invites_remaining <= 0:
        messages.error(request, "You don't have any remaining invites.")
        return HttpResponseRedirect(reverse("openach:index"))

    if request.method == 'POST':
        form = IssueInviteForm(request.POST, request=request)  # Pass the request
        if form.is_valid():
            invitee_email = form.cleaned_data['invitee_email']
            invitation = Invitation.objects.create(
                inviter=request.user,
                invitee_email=invitee_email
            )
            email = create_invitation_email(invitation, request)
            email.send()

            notify.send(request.user, recipient=invitation.invitee, verb='sent an invitation')

            messages.success(request, 'Invitation has been sent!')
            return HttpResponseRedirect(reverse("openach:index"))
    else:
        form = IssueInviteForm(request=request)  # Pass the request

    return render(request, 'boards/invite_form.html', {'form': form})


def create_invitation_email(invitation, request):
    """Return an invitation email message."""
    context = {
        'invitation': invitation,
        'site': get_current_site(request),
        'signup_url': reverse('signup_url')
    }

    subject = render_to_string(
        "boards/email/invitation_subject.txt", context=context
    )
    subject = " ".join(subject.splitlines()).strip()

    text_body = render_to_string(
        "boards/email/invitation_message.txt", context=context
    )
    html_body = render_to_string(
        "boards/email/invitation_message.html", context=context
    )

    email = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [invitation.invitee_email])
    email.attach_alternative(html_body, "text/html")
    return email
