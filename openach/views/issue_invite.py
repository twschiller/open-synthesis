from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site
from notifications.signals import notify

from openach.forms import IssueInviteForm
from openach.models import Invitation

PAGE_CACHE_TIMEOUT_SECONDS = getattr(settings, "PAGE_CACHE_TIMEOUT_SECONDS", 60)


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
