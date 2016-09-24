"""Custom account adapters."""

from allauth.account.adapter import DefaultAccountAdapter
from invitations.app_settings import app_settings

from .models import UserSettings


class InvitationsAdapter(DefaultAccountAdapter):
    """Django invitations adapter.

    Taken from https://github.com/bee-keeper/django-invitations/blob/master/invitations/models.py
    """

    # django-invitations does some hackery when using allauth in their models module.

    def is_open_for_signup(self, request):
        """Return True if site is not invitation only, or if the user accessed the signup from an invitation."""
        if hasattr(request, 'session') and request.session.get('account_verified_email'):
            return True
        elif app_settings.INVITATION_ONLY is True:
            # site is ONLY open for invites
            return False
        else:
            # site is open to signup
            return True


class AccountAdapter(InvitationsAdapter):
    """Account adapter to handle account actions, e.g., sign-up.

    For more information, see:
        https://django-allauth.readthedocs.io/en/latest/advanced.html#creating-and-populating-user-instances
    """

    def save_user(self, request, user, form, commit=True):
        """Initialize default settings for user when on signup."""
        saved = super().save_user(request, user, form, commit)
        UserSettings.objects.create(user=saved)
        return saved
