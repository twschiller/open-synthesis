"""Django admin command to send email digests."""
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone

from openach.models import DigestFrequency
from openach.digest import send_digest_emails


class Command(BaseCommand):
    """Django admin command to send out digest emails."""

    help = 'Send digest emails to users subscribed with the given frequency.'

    def add_arguments(self, parser):
        """Add 'frequency' and 'force' command arguments."""
        parser.add_argument('frequency', choices=['daily', 'weekly'])
        parser.add_argument('--force', nargs='?', dest='force', const=True, default=False,
                            help='Force the weekly digest to be sent regardless of day (default: False)')

    def report(self, cnt):
        """Report number of emails sent to STDOUT."""
        msg = 'Sent %s digest emails (%s skipped, %s failed)' % cnt
        self.stdout.write(self.style.SUCCESS(msg))  # pylint: disable=no-member

    def handle(self, *args, **options):
        """Handle the command invocation."""
        if options['frequency'] == 'daily':
            self.report(send_digest_emails(DigestFrequency.daily))
        elif options['frequency'] == 'weekly':
            digest_day = getattr(settings, 'DIGEST_WEEKLY_DAY')
            current_day = timezone.now().weekday()
            if current_day == digest_day or options['force']:
                if current_day != digest_day and options['force']:
                    msg = 'Forcing weekly digest to be sent (scheduled=%s, current=%s)' % (digest_day, current_day)
                    self.stdout.write(self.style.WARNING(msg))  # pylint: disable=no-member
                self.report(send_digest_emails(DigestFrequency.weekly))
            else:
                msg = 'Skipping weekly digest until day %s (current=%s)' % (digest_day, current_day)
                self.stdout.write(self.style.WARNING(msg))  # pylint: disable=no-member
        else:
            raise CommandError('Expected frequency "daily" or "weekly"')
