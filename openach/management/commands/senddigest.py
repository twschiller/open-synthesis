"""Django admin command to send email digests."""
from django.core.management.base import BaseCommand, CommandError

from openach.models import DigestFrequency
from openach.digest import send_digest_emails


class Command(BaseCommand):
    """Django admin command to send out digest emails."""

    help = 'Send digest emails to users subscribed with the given frequency.'

    def add_arguments(self, parser):
        """Add 'frequency' command argument."""
        parser.add_argument('frequency', choices=['daily', 'weekly'])

    def handle(self, *args, **options):
        """Handle the command invocation."""
        if options['frequency'] == 'daily':
            cnt = send_digest_emails(DigestFrequency.daily)
        elif options['frequency'] == 'weekly':
            cnt = send_digest_emails(DigestFrequency.weekly)
        else:
            raise CommandError('Expected frequency "daily" or "weekly"')

        msg = 'Sent %s digest emails (%s skipped, %s failed)' % cnt
        self.stdout.write(self.style.SUCCESS(msg))  # pylint: disable=no-member
