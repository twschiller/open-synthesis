import datetime
import logging

from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.utils import timezone
from unittest.mock import patch

from openach.digest import create_digest_email, send_digest_emails
from openach.models import Evidence, Hypothesis, BoardFollower, DigestFrequency
from openach.views import notify_add

from .common import PrimaryUserTestCase, create_board

logger = logging.getLogger(__name__)

DEFAULT_FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', 'admin@localhost')


class DigestTests(PrimaryUserTestCase):

    def setUp(self):
        super().setUp()
        self.daily = self.user
        self.weekly = self.other

        def setup_user(user, freq):
            user.date_joined = timezone.now() + datetime.timedelta(days=-2)
            user.save()
            user.settings.digest_frequency = freq.key
            user.settings.save()

        setup_user(self.daily, DigestFrequency.daily)
        setup_user(self.weekly, DigestFrequency.weekly)

    def test_can_create_first_digest(self):
        """Test that we can create a digest if the user hasn't received a digest before."""
        run_timestamp = timezone.now()
        create_board(board_title='New Board', days=-1)
        email = create_digest_email(self.daily, DigestFrequency.daily, run_timestamp)
        self.assertListEqual(email.to, [self.daily.email])
        logger.debug(email.subject)

        self.assertGreater(len(email.alternatives), 0, 'No HTML body attached to digest email')
        self.assertTrue('daily' in email.subject, 'No digest frequency in subject: {}'.format(email.subject))
        self.assertTrue('daily' in email.body)

    def test_can_email_first_daily_digest(self):
        """Test that we can email a digest if the user hasn't received a daily digest before."""
        create_board(board_title='New Board', days=0)
        succeeded, passed, failed = send_digest_emails(DigestFrequency.daily)
        self.assertEqual(succeeded, 1)
        self.assertEqual(passed, 0)
        self.assertEqual(failed, 0)
        self.assertEqual(len(mail.outbox), 1, 'No digest email sent')
        self.assertGreater(len(mail.outbox[0].alternatives), 0, 'No HTML body attached to digest email')
        self.assertListEqual(mail.outbox[0].to, [self.daily.email])
        self.assertEqual(mail.outbox[0].from_email, DEFAULT_FROM_EMAIL)

    def test_can_email_hypothesis_evidence_digest(self):
        """Test that we can email a digest containing new hypotheses and evidence."""
        for x in [1, 2]:
            board = create_board(board_title='Board #{}'.format(x), days=0)
            BoardFollower.objects.create(
                board=board,
                user=self.daily,
            )
            hypothesis = Hypothesis.objects.create(
                board=board,
                hypothesis_text='Hypothesis #{}'.format(x),
                creator=self.weekly,
            )
            evidence = Evidence.objects.create(
                board=board,
                evidence_desc='Evidence #{}'.format(x),
                creator=self.weekly,
            )
            notify_add(board, self.weekly, hypothesis)
            notify_add(board, self.weekly, evidence)

        succeeded, passed, failed = send_digest_emails(DigestFrequency.daily)
        self.assertEqual(succeeded, 1)
        self.assertEqual(len(mail.outbox), 1, 'No digest email sent')
        txt_body = mail.outbox[0].body
        logger.info(txt_body)

        for x in [1, 2]:
            self.assertTrue('Board #{}'.format(x) in txt_body)
            self.assertTrue('Hypothesis #{}'.format(x) in txt_body)
            self.assertTrue('Evidence #{}'.format(x) in txt_body)

    def test_email_digest_command(self):
        """Test that admin can send digest from a manage command."""
        create_board(board_title='New Board', days=0)
        call_command('senddigest', 'daily')
        self.assertEqual(len(mail.outbox), 1, 'No weekly digest email sent')

    def test_email_weekly_command_digest_day(self):
        """Test that admin can send digest on the weekly digest day."""
        setattr(settings, 'DIGEST_WEEKLY_DAY', 0)

        previous = timezone.now()
        static = previous
        # find the next scheduled digest day
        while static.weekday() != 0:
            static += timezone.timedelta(days=1)

        with patch('openach.management.commands.senddigest.timezone.now') as timezone_mock:
            timezone_mock.return_value = static
            logger.debug('Shifted timezone.now() from weekday %s to %s', previous.weekday(), static.weekday())

            create_board(board_title='New Board', days=-1)
            call_command('senddigest', 'weekly')

            self.assertEqual(len(mail.outbox), 1, 'No weekly digest email sent')

    def test_email_weekly_command_other_day(self):
        """Test that admin cannot digest email not on weekly digest day unless forced."""
        setattr(settings, 'DIGEST_WEEKLY_DAY', 0)

        previous = timezone.now()
        static = previous
        # make sure we're not on a scheduled digest day
        while static.weekday() == 0:
            static += timezone.timedelta(days=1)

        with patch('openach.management.commands.senddigest.timezone.now') as timezone_mock:
            timezone_mock.return_value = static
            logger.debug('Shifted timezone.now() from weekday %s to %s', previous.weekday(), static.weekday())

            create_board(board_title='New Board', days=-1)
            call_command('senddigest', 'weekly')

            self.assertEqual(len(mail.outbox), 0, 'Weekly digest email sent on wrong day')

            call_command('senddigest', 'weekly', '--force')
            self.assertEqual(len(mail.outbox), 1, 'Weekly digest email not sent when forced')

