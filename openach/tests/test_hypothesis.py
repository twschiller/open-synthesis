from django.urls import reverse

from openach.models import Hypothesis
from openach.views import HypothesisForm

from .common import PrimaryUserTestCase, create_board, add_follower


class AddEditHypothesisTests(PrimaryUserTestCase):

    def setUp(self):
        super().setUp()
        self.board = create_board('Test Board', days=5)
        self.hypotheses = [
            Hypothesis.objects.create(
                board=self.board,
                hypothesis_text='Hypothesis #1',
                creator=self.user,
            ),
            Hypothesis.objects.create(
                board=self.board,
                hypothesis_text='Hypothesis #2',
                creator=self.user,
            )
        ]
        self.follower = add_follower(self.board)

    def test_require_login_for_add_hypothesis(self):
        """Test that a user must be logged in  to access the add hypothesis form."""
        response = self.client.get(reverse('openach:add_hypothesis', args=(self.board.id,)))
        self.assertEqual(response.status_code, 302)

    def test_add_hypothesis_show_form(self):
        """Test that the add hypothesis form renders in a reasonable way."""
        self.login()
        response = self.client.get(reverse('openach:add_hypothesis', args=(self.board.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/add_hypothesis.html')

        # the view should display the existing hypotheses
        for hypothesis in self.hypotheses:
            self.assertContains(response, hypothesis.hypothesis_text)

        # the view should display the board name and description
        self.assertContains(response, self.board.board_title)
        self.assertContains(response, self.board.board_desc)

    def test_add_hypothesis_submit(self):
        """Test that the hypothesis is added to the database when the user submits the form."""
        self.login()
        text = 'Test Hypothesis 3'
        response = self.client.post(reverse('openach:add_hypothesis', args=(self.board.id,)), data={
            'hypothesis_text': text,
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(len(Hypothesis.objects.filter(hypothesis_text=text)), 0)
        self.assertTrue(self.board.has_follower(self.user))
        self.assertGreater(self.follower.notifications.unread().count(), 0)

    def test_hypothesis_edit_form(self):
        """Test that the form validation passes for valid input."""
        form = HypothesisForm({
            'hypothesis_text': 'My Hypothesis',
        })
        self.assertTrue(form.is_valid())

    def test_can_show_edit_form(self):
        """Test that the a user can view the hypothesis editing form."""
        self.login()
        response = self.client.get(reverse('openach:edit_hypothesis', args=(self.hypotheses[0].id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/edit_hypothesis.html')

    def test_can_submit_edit_form(self):
        """Test that the hypothesis text is updated via the form."""
        self.login()
        response = self.client.post(reverse('openach:edit_hypothesis', args=(self.hypotheses[0].id,)), data={
            'hypothesis_text': 'Updated Hypothesis',
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreaterEqual(len(Hypothesis.objects.filter(hypothesis_text='Updated Hypothesis')), 1)
        self.assertFalse(self.board.has_follower(self.user))
        self.assertGreater(self.follower.notifications.unread().count(), 0)

    def test_can_remove_hypothesis(self):
        """Test that the hypothesis is removed when the user clicks the remove button."""
        self.login()
        response = self.client.post(reverse('openach:edit_hypothesis', args=(self.hypotheses[0].id,)), data={
            'remove': 'remove',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(Hypothesis.objects.all()), 1)
        self.assertEqual(len(Hypothesis.all_objects.all()), 2)

