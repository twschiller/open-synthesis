from django.urls import reverse
from django.utils import timezone
from notifications.signals import notify

from openach.models import Board, Evidence, Hypothesis, Evaluation, Eval
from openach.models import DigestFrequency
from openach.views import SettingsForm


from .common import PrimaryUserTestCase


class ProfileTests(PrimaryUserTestCase):

    def setUp(self):
        super().setUp()

    def _add_board(self, user=None):
        self.board = Board.objects.create(
            board_title='Title',
            board_desc='Description',
            creator=user,
            pub_date=timezone.now(),
        )

    def _add_hypothesis(self, user=None):
        self.hypothesis = Hypothesis.objects.create(
            hypothesis_text='Hypothesis',
            creator=user,
            board=self.board
        )

    def _add_evidence(self, user=None):
        self.evidence = Evidence.objects.create(
            evidence_desc='Evidence',
            creator=user,
            board=self.board
        )

    def _add_eval(self, user=None):
        self.eval_ = Evaluation.objects.create(
            value=Eval.consistent.value,
            evidence=self.evidence,
            hypothesis=self.hypothesis,
            user=user,
            board=self.board,
        )

    def test_empty_public_activity(self):
        """Test that any user can access a public profile for user with no activity."""
        response = self.client.get(reverse('profile', args=(self.user.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/public_profile.html')
        self.assertContains(response, 'User {}'.format(self.user.username))
        self.assertNotContains(response, 'View All')
        self.assertContains(response, 'has not contributed to any boards')
        self.assertContains(response, 'has not evaluated any boards')
        self.assertContains(response, 'has not created any boards')

    def test_public_activity_creator(self):
        """Test public profile of user that has created a board."""
        self._add_board(self.user)
        response = self.client.get(reverse('profile', args=(self.user.id,)))
        self.assertTemplateUsed(response, 'boards/public_profile.html')
        self.assertContains(response, 'View All', count=1, status_code=200)
        self.assertContains(response, 'has not contributed to any boards')
        self.assertContains(response, 'has not evaluated any boards')

    def test_public_activity_creator_max_display(self):
        """Test that at most 3 boards are shown on the profile."""
        for x in range(1, 10):
            Board.objects.create(
                board_title='Title #{}'.format(x),
                board_desc='Description',
                creator=self.user,
                pub_date=timezone.now(),
            )
        response = self.client.get(reverse('profile', args=(self.user.id,)))
        self.assertContains(response, 'Title #', count=3, status_code=200)

    def test_private_profile_require_login(self):
        """Test that an anonymous user is redirected to the login page when attempting to view their private profile."""
        response = self.client.get(reverse('private_profile'))
        self.assertEqual(response.status_code, 302)

    def test_public_activity_contributor(self):
        """Test public profile of user that has contributed to a board."""
        self._add_board()
        self._add_evidence(self.user)
        self._add_hypothesis(self.user)
        response = self.client.get(reverse('profile', args=(self.user.id,)))
        self.assertTemplateUsed(response, 'boards/public_profile.html')
        self.assertContains(response, 'View All', count=1)
        self.assertContains(response, 'has not evaluated any boards')
        self.assertContains(response, 'has not created any boards')

    def test_public_activity_evaluator(self):
        """Test public profile of user that has evaluated a board."""
        self._add_board()
        self._add_evidence()
        self._add_hypothesis()
        self._add_eval(self.user)
        response = self.client.get(reverse('profile', args=(self.user.id,)))
        self.assertTemplateUsed(response, 'boards/public_profile.html')
        self.assertContains(response, 'View All', count=1)
        self.assertContains(response, 'has not contributed to any boards')
        self.assertContains(response, 'has not created any boards')

    def test_empty_private_activity(self):
        """Test that private profile for user with no activity."""
        self.login()
        response = self.client.get(reverse('profile', args=(self.user.id,)))
        self.assertTemplateUsed(response, 'boards/profile.html')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Welcome, {}'.format(self.user.username))
        self.assertNotContains(response, 'View All')
        self.assertContains(response, 'Create')
        self.assertContains(response, 'You have not created any boards.')
        self.assertContains(response, 'You have not contributed to any boards.')
        self.assertContains(response, 'You have not evaluated any boards.')

    def test_private_activity_creator(self):
        """Test private profile of user that has created a board."""
        self._add_board(self.user)
        self.login()
        response = self.client.get(reverse('profile', args=(self.user.id,)))
        self.assertTemplateUsed(response, 'boards/profile.html')
        self.assertContains(response, 'View All', count=1, status_code=200)
        self.assertContains(response, 'You have not contributed to any boards.')
        self.assertContains(response, 'You have not evaluated any boards.')

    def test_private_activity_contributor(self):
        """Test private profile of user that has contributed to a board."""
        self._add_board()
        self._add_evidence(self.user)
        self._add_hypothesis(self.user)
        self.login()
        response = self.client.get(reverse('profile', args=(self.user.id,)))
        self.assertTemplateUsed(response, 'boards/profile.html')
        self.assertContains(response, 'View All', count=1)
        self.assertContains(response, 'You have not created any boards.')
        self.assertContains(response, 'You have not evaluated any boards.')

    def test_private_activity_evaluator(self):
        """Test private profile of user that has evaluated a board."""
        self._add_board()
        self._add_evidence()
        self._add_hypothesis()
        self._add_eval(self.user)
        self.login()
        response = self.client.get(reverse('profile', args=(self.user.id,)))
        self.assertTemplateUsed(response, 'boards/profile.html')
        self.assertContains(response, 'View All', count=1)
        self.assertContains(response, 'You have not created any boards.')
        self.assertContains(response, 'You have not contributed to any boards.')

    def test_private_notifications(self):
        """Test that the profile page shows up to 5 notifications."""
        for x in range(0, 10):
            notify.send(self.other, recipient=self.user, actor=self.other, verb='said hello {}'.format(x))
        self.login()
        response = self.client.get(reverse('profile', args=(self.user.id,)))
        self.assertContains(response, 'said hello', status_code=200, count=5)

    def test_update_settings_form(self):
        """Test that settings form accepts a reasonable input."""
        for frequency in DigestFrequency:
            form = SettingsForm({'digest_frequency': frequency.key})
            self.assertTrue(form.is_valid())

    def test_update_settings(self):
        """Test that the user can update their digest frequency."""
        self.user.settings.digest_frequency = DigestFrequency.never.key
        self.user.settings.save()
        self.login()
        response = self.client.post('/accounts/profile/', data={
            'digest_frequency':  str(DigestFrequency.weekly.key),
        })
        self.assertEqual(response.status_code, 200)
        self.user.settings.refresh_from_db()
        self.assertEqual(self.user.settings.digest_frequency, DigestFrequency.weekly.key)


