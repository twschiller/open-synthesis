from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings

DEFAULT_FROM_EMAIL = getattr(settings, "DEFAULT_FROM_EMAIL", "admin@localhost")


class AccountManagementTests(TestCase):
    """Project-specific account management tests. General tests should be in the django-allauth library."""

    username = "testuser"

    email = "testemail@google.com"

    valid_data = {
        "username": username,
        "email": email,
        "password1": "testpassword1!",
        "password2": "testpassword1!",
    }

    @override_settings(
        INVITATIONS_INVITATION_ONLY=False, INVITE_REQUEST_URL="https://google.com"
    )
    def test_can_show_signup_form(self):
        """Test that a non-logged-in user can view the sign-up form."""
        response = self.client.get("/accounts/signup/")
        self.assertTemplateUsed("/account/email/signup.html")
        self.assertNotContains(response, "invitation")

    @override_settings(
        INVITATIONS_INVITATION_ONLY=True, INVITE_REQUEST_URL="https://google.com"
    )
    def test_can_show_invite_url(self):
        """Test that a non-logged-in user can view the sign-up form that has an invite link."""
        response = self.client.get("/accounts/signup/")
        self.assertContains(response, "invitation")

    @override_settings(ACCOUNT_EMAIL_REQUIRED=True)
    def test_email_address_required(self):
        """Test that signup without email is rejected."""
        response = self.client.post(
            "/accounts/signup/", data={**self.valid_data, "email": ""}
        )
        self.assertTemplateUsed("account/signup.html")
        # behavior is for the form-group of the email address to have has-error and to have its help text set
        self.assertContains(response, "This field is required.")

    @override_settings(
        ACCOUNT_EMAIL_REQUIRED=True, ACCOUNT_EMAIL_VERIFICATION="mandatory"
    )
    @patch("allauth.account.signals.email_confirmation_sent.send")
    def test_account_signup_flow(self, mock):
        """Test that the user receives a confirmation email when they signup for an account with an email address."""
        response = self.client.post("/accounts/signup/", data=self.valid_data)
        self.assertRedirects(response, expected_url="/accounts/confirm-email/")

        self.assertEqual(mock.call_count, 1)
        self.assertEqual(len(mail.outbox), 1, "No confirmation email sent")

        # The example.com domain comes from django.contrib.sites plugin
        self.assertEqual(
            mail.outbox[0].subject, "[example.com] Please Confirm Your E-mail Address"
        )
        self.assertListEqual(mail.outbox[0].to, [self.email])
        self.assertEqual(mail.outbox[0].from_email, DEFAULT_FROM_EMAIL)

    @override_settings(ACCOUNT_EMAIL_REQUIRED=False)
    def test_settings_created(self):
        """Test that a settings object is created when the user is created."""
        self.client.post("/accounts/signup/", data=self.valid_data)
        user = User.objects.get(username=self.username)
        self.assertIsNotNone(user.settings, "User settings object not created")
