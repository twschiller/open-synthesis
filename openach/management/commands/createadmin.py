"""Django admin command to create an admin account based on the project settings."""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """Django admin command to create an admin account based on the project settings variables.

    Requires the following settings: ADMIN_USERNAME, ADMIN_PASSWORD, ADMIN_EMAIL_ADDRESS.
    """

    help = "Automatically create superuser based on environment variables."

    def handle(self, *args, **options):
        """Handle the command invocation."""
        email = getattr(settings, "ADMIN_EMAIL_ADDRESS", None)
        username = getattr(settings, "ADMIN_USERNAME", None)
        password = getattr(settings, "ADMIN_PASSWORD", None)

        if not email or not username or not password:
            raise CommandError(
                "ADMIN_USERNAME, ADMIN_PASSWORD, and ADMIN_EMAIL_ADDRESS must be set"
            )

        admin = User(username=username, email=email)
        admin.set_password(password)
        admin.is_superuser = True
        admin.is_staff = True
        admin.save()

        msg = f"Successfully configured admin {username} ({email})"
        self.stdout.write(self.style.SUCCESS(msg))  # pylint: disable=no-member
