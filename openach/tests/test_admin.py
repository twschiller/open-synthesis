from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase

DEFAULT_FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', 'admin@localhost')


class AccountManagementTests(TestCase):
    """Project-specific account management tests. General tests should be in the django-allauth library."""

    username = 'testuser'
    email = 'testemail@google.com'
    valid_data = {
        'username': username,
        'email': email,
        'password1': 'testpassword1!',
        'password2': 'testpassword1!',
    }

    def test_can_show_signup_form(self):
        """Test that a non-logged-in user can view the sign-up form."""
        setattr(settings, 'INVITATIONS_INVITATION_ONLY', False)
        setattr(settings, 'INVITE_REQUEST_URL', 'https://google.com')
        response = self.client.get('/accounts/signup/')
        self.assertTemplateUsed('/account/email/signup.html')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'invitation')

    def test_can_show_invite_url(self):
        """Test that a non-logged-in user can view the sign-up form that has an invite link."""
        setattr(settings, 'INVITATIONS_INVITATION_ONLY', True)
        setattr(settings, 'INVITE_REQUEST_URL', 'https://google.com')
        response = self.client.get('/accounts/signup/')
        self.assertContains(response, 'invitation')

    def test_email_address_required(self):
        """Test that signup without email is rejected."""
        setattr(settings, 'ACCOUNT_EMAIL_REQUIRED', True)
        response = self.client.post('/accounts/signup/', data={**self.valid_data, 'email': None})
        self.assertContains(response, 'Enter a valid email address.', status_code=200)

    def test_account_signup_flow(self):
        """Test that the user receives a confirmation email when they signup for an account with an email address."""
        setattr(settings, 'ACCOUNT_EMAIL_REQUIRED', True)
        response = self.client.post('/accounts/signup/', data=self.valid_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1, 'No confirmation email sent')
        # The example.com domain comes from django.contrib.sites plugin
        self.assertEqual(mail.outbox[0].subject, '[example.com] Please Confirm Your E-mail Address')
        self.assertListEqual(mail.outbox[0].to, [self.email])
        self.assertEqual(mail.outbox[0].from_email, DEFAULT_FROM_EMAIL)

    def test_settings_created(self):
        """Test that a settings object is created when the user is created."""
        setattr(settings, 'ACCOUNT_EMAIL_REQUIRED', False)
        self.client.post('/accounts/signup/', data=self.valid_data)
        user = User.objects.filter(username=self.username).first()
        self.assertIsNotNone(user.settings, 'User settings object not created')
