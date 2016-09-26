"""Methods for creating/sending notification digests."""
import logging
import collections

from django.utils import timezone
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives, get_connection
from django.contrib.sites.models import Site

from .models import DigestStatus, Board, UserSettings, DigestFrequency


logger = logging.getLogger(__name__)   # pylint: disable=invalid-name


def notification_digest(user, start, end):
    """Return digest for user with content/notifications occurring after start.

    Notifications are grouped by target, e.g., board.

    :param user: the user
    :param start: the start datetime for the the digest
    :param end: the end datetime for the digest
    """
    notifications = user.notifications.unread().filter(timestamp__gt=start, timestamp__lt=end)
    by_target = collections.defaultdict(list)
    for notification in notifications:
        if notification.target and notification.actor.id != user.id:
            by_target[notification.target].append(notification)

    new_boards = Board.objects.all().filter(pub_date__gt=start, pub_date__lt=end).exclude(creator_id=user.id)
    if notifications.exists() or new_boards.exists():
        return {
            'new_boards': new_boards,
            # https://code.djangoproject.com/ticket/16335
            'notifications': dict(by_target)
        }
    else:
        return None


def user_digest_start(user, digest_frequency, as_of):
    """Return the starting datetime for a digest for user.

    :param user: the user to create the digest for
    :param digest_frequency: the DigestFrequency for the digest
    :param as_of: the datetime to generate the digest for
    """
    # NOTE: this is inefficient for multiple users because we have to hit the DB for each one
    if digest_frequency == DigestFrequency.never:
        raise ValueError('Digest frequency cannot be "never"')

    digest = as_of - digest_frequency.delta
    join = user.date_joined
    status = DigestStatus.objects.filter(user=user).first()
    previous = status.last_success if (status and status.last_success) else join
    return max([digest, join, previous])


def create_digest_email(user, digest_frequency, as_of):
    """Return the digest email message for user based on when they last received a digest message."""
    start = user_digest_start(user, digest_frequency, as_of)
    context = notification_digest(user, start, as_of)

    logger.debug('Digest as of %s: %s', start, context)

    if context:
        context['timestamp'] = as_of
        context['site'] = Site.objects.get_current()
        context['digest_frequency'] = digest_frequency.name

        subject = render_to_string('boards/email/email_digest_subject.txt', context=context)
        # remove superfluous line breaks
        subject = " ".join(subject.splitlines()).strip()

        text_body = render_to_string('boards/email/email_digest_message.txt', context=context)
        html_body = render_to_string('boards/email/email_digest_message.html', context=context)

        email = EmailMultiAlternatives(subject=subject, body=text_body, to=[user.email])
        email.attach_alternative(html_body, "text/html")
        return email
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
        UserSettings.objects.filter(digest_frequency=digest_frequency.key).select_related('user')
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
