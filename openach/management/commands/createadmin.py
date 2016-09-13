"""Django admin command to create an admin account based on the environment variables"""
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Automatically create superuser based on environment variables.'

    def handle(self, *args, **options):
        email = getattr(settings, 'ADMIN_EMAIL_ADDRESS', None)
        username = getattr(settings, 'ADMIN_USERNAME', None)
        password = getattr(settings, 'ADMIN_PASSWORD', None)

        if not email or not username or not password:
            raise CommandError('ADMIN_USERNAME, ADMIN_PASSWORD, and ADMIN_EMAIL_ADDRESS must be set')

        admin = User(username=username, email=email)
        admin.set_password(password)
        admin.is_superuser = True
        admin.is_staff = True
        admin.save()

        self.stdout.write(self.style.SUCCESS('Successfully configured admin %s (%s)' % (username, email)))
