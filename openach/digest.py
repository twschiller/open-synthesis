"""Methods for creating/sending notification digests."""
import logging

from django.utils import timezone
from django.template.loader import render_to_string
from django.core.mail import EmailMessage, get_connection
from django.contrib.sites.models import Site

from .models import DigestStatus, Board, UserSettings, DigestFrequency


logger = logging.getLogger(__name__)   # pylint: disable=invalid-name


def notification_digest(user, since):
    """Return digest for user with content/notifications occurring after since.

    :param user: the user
    :param since: the base timestamp or None, for example, the last time a digest was sent
    """
    notifications = user.notifications.unread().filter(timestamp__gt=since)
    new_boards = Board.objects.all().filter(pub_date__gt=since).exclude(creator_id=user.id)
    if notifications.exists() or new_boards.exists():
        return {
            'new_boards': new_boards,
            'notifications': notifications
        }
    else:
        return None


def user_digest_base_datetime(user):
    """Return the timestamp of the user's last digest, or the date the joined."""
    # NOTE: this is inefficient for multiple users because we have to hit the DB for each one
    status = DigestStatus.objects.filter(user=user).first()
    return status.last_success if (status and status.last_success) else user.date_joined


def create_digest_email(user, digest_frequency, run_timestamp):
    """Return the digest email message for user based on when they last received a digest message."""
    timestamp = user_digest_base_datetime(user)
    context = notification_digest(user, timestamp)

    if context:
        context['timestamp'] = run_timestamp
        context['site'] = Site.objects.get_current()
        context['digest_frequency'] = digest_frequency.name

        subject = render_to_string('boards/email/email_digest_subject.txt', context=context)
        # remove superfluous line breaks
        subject = " ".join(subject.splitlines()).strip()

        body = render_to_string('boards/email/email_digest_message.txt', context=context)

        return EmailMessage(subject=subject, body=body, to=[user.email])
    else:
        return None


def send_digest_emails(digest_frequency):
    """Send daily digests to users subscribed to digests with frequency digest_frequency.

    :return tuple containing number of emails successfully sent and number that failed to send
    """
    if digest_frequency == DigestFrequency.never:
        raise ValueError('Cannot send digest emails for frequency "never"')

    timestamp = timezone.now()
    subscribers = [
        u.user for u in
        UserSettings.objects.filter(digest_frequency=digest_frequency.value).select_related('user')
    ]
    emails = [(u, create_digest_email(u, digest_frequency, timestamp)) for u in subscribers]

    succeeded = 0
    skipped = 0
    failed = 0

    with get_connection(fail_silently=False):
        for user, email in emails:
            if email:
                try:
                    email.send()
                    DigestStatus.objects.update_or_create(user=user, defaults={
                        'last_success': timestamp,
                        'last_attempt': timestamp
                    })
                    logger.debug('Sent digest email to %s', user)
                    succeeded += 1
                except Exception as ex:
                    logger.error('Error sending digest to %s', user, exc_info=ex)
                    DigestStatus.objects.update_or_create(user=user, defaults={
                        'last_attempt': timestamp
                    })
                    failed += 1
            else:
                logger.debug('User %s has no new updates for digest', user)
                skipped += 1

    return succeeded, skipped, failed
