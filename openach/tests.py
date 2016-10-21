import datetime
import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django_comments.models import Comment
from field_history.models import FieldHistory
from notifications.signals import notify
from unittest.mock import patch, PropertyMock

from .digest import create_digest_email, send_digest_emails
from .metrics import hypothesis_sort_key, evidence_sort_key
from .metrics import inconsistency, consistency, proportion_na, proportion_unevaluated
from .metrics import mean_na_neutral_vote, consensus_vote, diagnosticity, calc_disagreement
from .models import Board, Evidence, Hypothesis, Evaluation, Eval, ProjectNews, BoardFollower, URL_MAX_LENGTH
from .models import UserSettings, DigestFrequency
from .sitemap import BoardSitemap
from .tasks import example_task, parse_metadata, fetch_source_metadata
from .util import first_occurrences
from .views import bitcoin_donation_url, notify_edit, notify_add
from .views import EvidenceSource, EvidenceSourceTag, AnalystSourceTag
from .views import SettingsForm, BoardForm, EvidenceSourceForm, HypothesisForm, EvidenceForm


logger = logging.getLogger(__name__)


DEFAULT_FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', 'admin@localhost')
SLUG_MAX_LENGTH = getattr(settings, 'SLUG_MAX_LENGTH')


def remove(model):
    """Mark model as removed."""
    model.removed = True
    model.save()


def follows(user, board):
    """Return True iff user follows board."""
    return BoardFollower.objects.filter(user=user, board=board).exists()


def add_follower(board):
    follower = User.objects.create_user('bob', 'bob@thebeatles.com', 'bobpassword')
    BoardFollower.objects.create(
        user=follower,
        board=board,
    )
    return follower


class UtilMethodTests(TestCase):

    def test_first_occurrences_empty(self):
        """Test that first_instances() returns an empty list when an empty list is provided."""
        self.assertEqual(first_occurrences([]), [])

    def test_first_occurrences(self):
        """Test that first_instances() only preserves the first occurrence in the list."""
        self.assertEqual(first_occurrences(['a', 'a']), ['a'])
        self.assertEqual(first_occurrences(['a', 'b', 'a']), ['a', 'b'])


class BoardMethodTests(TestCase):

    def test_was_published_recently_with_future_board(self):
        """Test that was_published_recently() returns False for board whose pub_date is in the future."""
        time = timezone.now() + datetime.timedelta(days=30)
        future_board = Board(pub_date=time)
        self.assertIs(future_board.was_published_recently(), False)

    def test_was_published_recently_with_old_question(self):
        """Test that was_published_recently() returns False for boards whose pub_date is older than 1 day."""
        time = timezone.now() - datetime.timedelta(days=30)
        old_board = Board(pub_date=time)
        self.assertIs(old_board.was_published_recently(), False)

    def test_was_published_recently_with_recent_question(self):
        """Test that was_published_recently() returns True for boards whose pub_date is within the last day."""
        time = timezone.now() - datetime.timedelta(hours=1)
        recent_board = Board(pub_date=time)
        self.assertIs(recent_board.was_published_recently(), True)

    def test_board_url_without_slug(self):
        """Test to make sure we can grab the URL of a board that has no slug."""
        self.assertIsNotNone(Board(id=1).get_absolute_url())

    def test_board_url_with_slug(self):
        """Test to make sure we can grab the URL of a board that has a slug."""
        slug = 'test-slug'
        self.assertTrue(slug in Board(id=1, board_slug=slug).get_absolute_url())


class RemovableModelManagerTests(TestCase):

    def test_objects_does_not_include_removed(self):
        """Test that after an object is marked as removed, it doesn't appear in the query set."""
        board = Board.objects.create(
            board_title='Title',
            board_desc='Description',
            pub_date=timezone.now()
        )
        self.assertEqual(Board.objects.count(), 1)
        remove(board)
        self.assertEqual(Board.objects.count(), 0)
        self.assertEqual(Board.all_objects.count(), 1)


class BoardFormTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')

    def test_create_board_requires_login(self):
        """Test that the board creation form requires the user to be logged in."""
        response = self.client.get(reverse('openach:create_board'))
        self.assertEqual(response.status_code, 302)

    def test_show_create_board_form(self):
        """Test that a logged in user can view the board creation form."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:create_board'))
        self.assertTemplateUsed(response, 'boards/create_board.html')
        self.assertEqual(response.status_code, 200)

    def test_submit_valid_create_board(self):
        """Test that a logged in user can create a board via the form creation."""
        self.client.login(username='john', password='johnpassword')
        title = 'Test Board Title'
        response = self.client.post(reverse('openach:create_board'), data={
            'board_title': title,
            'board_desc': 'Test Board Description',
            'hypothesis1': 'Test Hypotheses #1',
            'hypothesis2': 'Test Hypotheses #2',
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(len(Board.objects.filter(board_title=title)), 0)
        self.assertGreater(len(Board.objects.filter(board_slug='test-board-title')), 0)
        board = Board.objects.filter(board_title=title).first()
        self.assertTrue(follows(self.user, board))

    def test_submit_valid_create_board_long_title(self):
        """Test that a user can create a board with a long name and that the slug will be truncated."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:create_board'), data={
            'board_title': 'x' * (SLUG_MAX_LENGTH + 5),
            'board_desc': 'Test Board Description',
            'hypothesis1': 'Test Hypotheses #1',
            'hypothesis2': 'Test Hypotheses #2',
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(len(Board.objects.filter(board_slug='x' * SLUG_MAX_LENGTH)), 0)

    def test_board_edit_form(self):
        """Test that the board editing form validates for reasonable input."""
        form = BoardForm({
            'board_title': 'New board title',
            'board_desc': 'New board description',
        })
        self.assertTrue(form.is_valid())

    def test_can_show_edit_form(self):
        """Test that a logged in user can view the board edit form."""
        board = Board.objects.create(board_title='Board #1', creator=self.user, pub_date=timezone.now())
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:edit_board', args=(board.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/edit_board.html')
        self.assertNotContains(response, 'Remove Board')

    def test_staff_edit_form_has_remove_button(self):
        """Test that the edit form contains a remove button for staff."""
        board = Board.objects.create(board_title='Board #1', creator=self.user, pub_date=timezone.now())
        self.user.is_staff = True
        self.user.save()
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:edit_board', args=(board.id,)))
        self.assertContains(response, 'Remove Board', status_code=200)

    def test_non_owner_cannot_edit(self):
        """Test that the form is not displayed to the user that did not create the board."""
        setattr(settings, 'EDIT_AUTH_ANY', False)
        board = Board.objects.create(board_title='Board #1', creator=None, pub_date=timezone.now())
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:edit_board', args=(board.id,)))
        self.assertEqual(response.status_code, 403)

    def test_can_submit_edit_form(self):
        """Test that a logged in user can edit a board by submitting the form."""
        board = Board.objects.create(board_title='Board #1', creator=self.user, pub_date=timezone.now())

        # board initially has 3 changed fields: title, description, and if it has been removed
        self.assertEqual(FieldHistory.objects.get_for_model(board).count(), 3)

        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:edit_board', args=(board.id,)), data={
            'board_title': 'New Board Title',
            'board_desc': 'New Board Description',
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreaterEqual(len(Board.objects.filter(board_title='New Board Title')), 1)
        self.assertGreaterEqual(len(Board.objects.filter(board_desc='New Board Description')), 1)

        # check that field history was recorded
        self.assertEqual(FieldHistory.objects.get_for_model_and_field(board, 'board_title').count(), 2)
        self.assertEqual(FieldHistory.objects.get_for_model_and_field(board, 'board_desc').count(), 2)

    def test_can_remove_board(self):
        """Test that staff can mark a board as removed via the form."""
        board = Board.objects.create(board_title='Board #1', creator=self.user, pub_date=timezone.now())
        self.user.is_staff = True
        self.user.save()
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:edit_board', args=(board.id,)), data={
            'remove': 'remove'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Board.objects.count(), 0)
        self.assertEqual(Board.all_objects.count(), 1)

    def test_non_owner_cannot_remove_board(self):
        """Test that a random user can't delete the board using a POST request."""
        board = Board.objects.create(board_title='Board #1', creator=None, pub_date=timezone.now())
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:edit_board', args=(board.id,)), data={
            'remove': 'remove'
        })
        self.assertEqual(response.status_code, 403)

    def test_can_view_board_history(self):
        """Test that the board history shows a change in board title and description."""
        board = Board.objects.create(board_title='Board #1', creator=self.user, pub_date=timezone.now())
        self.client.login(username='john', password='johnpassword')
        self.client.post(reverse('openach:edit_board', args=(board.id,)), data={
            'board_title': 'New Board Title',
            'board_desc': 'New Board Description',
        })
        response = self.client.get(reverse('openach:board_history', args=(board.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/board_audit.html')
        self.assertContains(response, 'New Board Title')
        self.assertContains(response, 'New Board Description')

    def test_can_view_evidence_history(self):
        """Test that the board history shows the history of evidence that has been removed."""
        board = Board.objects.create(board_title='Board #1', creator=self.user, pub_date=timezone.now())
        evidence = Evidence.objects.create(board=board, evidence_desc='Evidence')
        remove(evidence)
        response = self.client.get(reverse('openach:board_history', args=(board.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, evidence.evidence_desc)


class BoardSearchTests(TestCase):

    def test_can_search_board_by_title(self):
        """Test that a client can search for boards by title."""
        create_board("abc", days=-1)
        create_board("xyz", days=-1)
        response = self.client.get(reverse('openach:board_search') + "?query=ab")
        self.assertContains(response, "abc", status_code=200)
        self.assertNotContains(response, "xyz", status_code=200)

    def test_can_search_by_board_description(self):
        """Test that a client can search for boards by description."""
        board = create_board("abc", days=-1)
        board.board_desc = "xyz"
        board.save()
        create_board("xyz", days=-1)
        response = self.client.get(reverse('openach:board_search') + "?query=xy")
        self.assertContains(response, "abc", status_code=200)


class SitemapTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
        self.board = create_board('Test Board', days=-5)
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc='Evidence #1',
            event_date=None,
        )
        self.hypotheses = [
            Hypothesis.objects.create(
                board=self.board,
                hypothesis_text='Hypothesis #1',
                creator=self.user,
            )
        ]

    def test_can_get_items(self):
        """Test that we can get all the boards."""
        sitemap = BoardSitemap()
        self.assertEqual(len(sitemap.items()), 1, 'Sitemap included removed board')

    def test_cannot_get_removed_items(self):
        """Test that the sitemap doesn't include removed boards."""
        remove(self.board)
        sitemap = BoardSitemap()
        self.assertEqual(len(sitemap.items()), 0)

    def test_can_get_last_update(self):
        """Test that sitemap uses the latest change."""
        latest = Hypothesis.objects.create(
            board=self.board,
            hypothesis_text='Hypothesis #2',
            creator=self.user,
        )
        sitemap = BoardSitemap()
        board = sitemap.items()[0]
        self.assertEqual(sitemap.lastmod(board), latest.submit_date)


class EvidenceAssessmentTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
        self.board = create_board('Test Board', days=5)
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc='Evidence #1',
            event_date=None,
        )
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

    def test_require_login_for_assessment(self):
        """Test that a user must be logged in in to access the evidence evaluation screen."""
        response = self.client.get(reverse('openach:evaluate', args=(self.board.id, self.evidence.id,)))
        self.assertEqual(response.status_code, 302)

    def test_evidence_assessment_form_renders(self):
        """Test that the evidence assessment form renders in a reasonable way."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:evaluate', args=(self.board.id, self.evidence.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/evaluate.html')
        for hypothesis in self.hypotheses:
            self.assertContains(response, hypothesis.hypothesis_text)

    def test_evidence_assessment_form_submit(self):
        """Test that the evidence assessment form can handle a submit"""
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:evaluate', args=(self.board.id, self.evidence.id)), data={
            'hypothesis-{}'.format(self.hypotheses[0].id): '0',
            'hypothesis-{}'.format(self.hypotheses[1].id): '1'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Evaluation.objects.count(), 2, msg='Expecting 2 evaluation objects')
        self.assertTrue(follows(self.user, self.board))


class AddEditHypothesisTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
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
        self.client.login(username='john', password='johnpassword')
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
        self.client.login(username='john', password='johnpassword')
        text = 'Test Hypothesis 3'
        response = self.client.post(reverse('openach:add_hypothesis', args=(self.board.id,)), data={
            'hypothesis_text': text,
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(len(Hypothesis.objects.filter(hypothesis_text=text)), 0)
        self.assertTrue(follows(self.user, self.board))
        self.assertGreater(self.follower.notifications.unread().count(), 0)

    def test_hypothesis_edit_form(self):
        """Test that the form validation passes for valid input."""
        form = HypothesisForm({
            'hypothesis_text': 'My Hypothesis',
        })
        self.assertTrue(form.is_valid())

    def test_can_show_edit_form(self):
        """Test that the a user can view the hypothesis editing form."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:edit_hypothesis', args=(self.hypotheses[0].id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/edit_hypothesis.html')

    def test_can_submit_edit_form(self):
        """Test that the hypothesis text is updated via the form."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:edit_hypothesis', args=(self.hypotheses[0].id,)), data={
            'hypothesis_text': 'Updated Hypothesis',
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreaterEqual(len(Hypothesis.objects.filter(hypothesis_text='Updated Hypothesis')), 1)
        self.assertFalse(follows(self.user, self.board))
        self.assertGreater(self.follower.notifications.unread().count(), 0)

    def test_can_remove_hypothesis(self):
        """Test that the hypothesis is removed when the user clicks the remove button."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:edit_hypothesis', args=(self.hypotheses[0].id,)), data={
            'remove': 'remove',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(Hypothesis.objects.all()), 1)
        self.assertEqual(len(Hypothesis.all_objects.all()), 2)


class BoardListingTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')

    def test_can_show_board_listing_no_page(self):
        """Test that board listing renders when no page number is provided."""
        board = create_board('Test Board', days=0)
        response = self.client.get(reverse('openach:boards'))
        self.assertTemplateUsed(response, 'boards/boards.html')
        self.assertContains(response, board.board_title, status_code=200)
        self.assertContains(response, '1')

    def test_can_show_board_listing_first_page(self):
        """Test board listing for when the first page is provided."""
        board = create_board('Test Board', days=0)
        response = self.client.get(reverse('openach:boards') + '?page=1')
        self.assertContains(response, board.board_title, status_code=200)
        self.assertContains(response, '1')

    def test_pagination(self):
        """Test that the correct boards show up on each page."""
        for x in range(1, 30):
            # views shows boards in order descending publishing data; set data so board n is published after board n+1
            create_board('Test Board {}'.format(x), days=100-x)
        response = self.client.get(reverse('openach:boards') + '?page=1')
        self.assertContains(response, 'Test Board 1', status_code=200)
        response = self.client.get(reverse('openach:boards') + '?page=2')
        self.assertContains(response, 'Test Board 15', status_code=200)

    def test_user_board_view(self):
        """Test board listing for user that created a board."""
        Board.objects.create(
            creator=self.user,
            board_title='Board Title',
            board_desc='Description',
            pub_date=timezone.now()
        )
        response = self.client.get(reverse('openach:user_boards', args=(self.user.id, ))+'?query=created')
        self.assertContains(response, 'Board Title', status_code=200)


class BannerTests(TestCase):

    def test_show_banner(self):
        """Test that the banner message shows on all pages."""
        msg = 'Test banner message'
        setattr(settings, 'BANNER_MESSAGE', msg)
        for page in ['index', 'boards', 'about']:
            response = self.client.get(reverse('openach:{}'.format(page)))
            self.assertContains(response, msg, status_code=200)

    def test_do_not_show_empty_banner(self):
        """Test that the banner alert doesn't appear when a BANNER_MESSAGE is not set."""
        # this test implementation actually just tests that we can render the page. there's no oracle for making sure
        # an empty alert div is not being shown.
        setattr(settings, 'BANNER_MESSAGE', None)
        response = self.client.get(reverse('openach:index'))
        self.assertEqual(response.status_code, 200)


class BoardDetailTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
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

    def _add_eval(self, hypothesis, user, eval):
        Evaluation.objects.create(
            board=self.board,
            hypothesis=hypothesis,
            evidence=self.evidence,
            user=user,
            value=eval.value,
        )

    def _add_evidence(self):
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc='Evidence #1',
            event_date=None,
        )

    def test_can_display_board_with_no_evidence(self):
        """Test that the detail view renders for a board with no evidence."""
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertEqual(response.status_code, 200)

        for hypothesis in self.hypotheses:
            self.assertContains(response, hypothesis.hypothesis_text)

    def test_can_display_board_with_no_assessments(self):
        """Test that the detail view renders for a board with no assessments."""
        self._add_evidence()
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.evidence.evidence_desc)

    def test_can_display_board_with_assessments_from_single_user(self):
        """Test that the detail view renders for a board with assessments from a single user."""
        self._add_evidence()
        self._add_eval(self.hypotheses[0], self.user, Eval.consistent)
        self._add_eval(self.hypotheses[1], self.user, Eval.inconsistent)
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertContains(response, 'Consistent', status_code=200)
        self.assertContains(response, 'Inconsistent', status_code=200)

    def test_can_display_board_with_multiple_assessments(self):
        """Test that the detail view displays merge assessments from multiple users."""
        self._add_evidence()
        other = User.objects.create_user('paul', 'mccartney@thebeatles.com', 'paulpassword')
        self._add_eval(self.hypotheses[0], self.user, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], self.user, Eval.inconsistent)
        self._add_eval(self.hypotheses[0], other, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], other, Eval.consistent)
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertEqual(response.status_code, 200)

    def test_can_display_comments(self):
        """Test that the detail view includes comments about the board."""
        comment = Comment.objects.create(
            content_type=ContentType.objects.get_for_model(Board),
            object_pk=self.board.id,
            user=self.user,
            user_url='http://example.com/~frank/',
            comment='First post.',
            site=Site.objects.get_current(),
        )
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertContains(response, 'Comments')
        self.assertContains(response, comment.comment)

    def test_display_comment_form_when_logged_in(self):
        """Test that the detail view shows a comment entry form for logged in users."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertContains(response, 'Add comment')

    def test_do_not_display_comparison_button_when_logged_out(self):
        """Test that the comparison view option is not displayed to anonymous users."""
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertNotContains(response, 'Comparison')

    def test_display_comparison_button_when_logged_in(self):
        """Test that the comparison view option is displayed for logged in users."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertContains(response, 'Comparison')

    def test_can_display_disagreement_with_no_assessments(self):
        """Test that the disagreement view option is displayed for all users."""
        self._add_evidence()
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)) + '?view_type=disagreement')
        self.assertEqual(response.status_code, 200)

    def test_can_display_disagreement_with_multiple_assessments(self):
        """Test that the disagreement view renders when there are assessments from multiple users."""
        self._add_evidence()
        other = User.objects.create_user('paul', 'mccartney@thebeatles.com', 'paulpassword')
        self._add_eval(self.hypotheses[0], self.user, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], self.user, Eval.very_consistent)
        self._add_eval(self.hypotheses[0], other, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], other, Eval.very_inconsistent)
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)) + '?view_type=disagreement')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Extreme Dispute')

    def test_can_display_comparison_no_assessments(self):
        """Test that the comparison view renders when there are no assessments."""
        self._add_evidence()
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)) + '?view_type=comparison')
        self.assertEqual(response.status_code, 200)

    def test_can_display_comparison(self):
        """Test that the comparison view renders when the user has provided assessments against a consensus."""
        self._add_evidence()
        other = User.objects.create_user('paul', 'mccartney@thebeatles.com', 'paulpassword')
        self._add_eval(self.hypotheses[0], self.user, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], self.user, Eval.inconsistent)
        self._add_eval(self.hypotheses[0], other, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], other, Eval.consistent)
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)) + '?view_type=comparison')
        self.assertEqual(response.status_code, 200)

    def test_order_hypotheses_and_evidence(self):
        """Test that the board detail views order evidence by diagnosticity and hypotheses by consistency."""
        def mk_evidence(desc):
            return Evidence.objects.create(board=self.board, creator=self.user, evidence_desc=desc, event_date=None)

        def mk_eval(hypothesis, evidence, eval_):
            Evaluation.objects.create(board=self.board, hypothesis=hypothesis, evidence=evidence, user=self.user, value=eval_.value)

        # put neutral evidence first so it's PK will be lower (and will probably be returned first by the DB)
        neutral = mk_evidence('Neutral Evidence')
        diagnostic = mk_evidence('Diagnostic Evidence')

        # make the consistent hypothesis first (it's PK is lower and will be returned first by the DB)
        mk_eval(self.hypotheses[0], diagnostic, Eval.inconsistent)
        mk_eval(self.hypotheses[1], diagnostic, Eval.consistent)
        mk_eval(self.hypotheses[0], neutral, Eval.neutral)
        mk_eval(self.hypotheses[1], neutral, Eval.neutral)

        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))

        self.assertGreater(len([scored for scored in response.context['evidences'] if scored[1][0] < 0.0]), 0,
                           msg='No evidence marked as diagnostic')
        self.assertGreater(len([scored for scored in response.context['hypotheses'] if scored[1][0] > 0.0]), 0,
                           msg='No evidence marked as inconsistent')

        self.assertEqual(response.context['evidences'][0][0], diagnostic,
                         msg='Diagnostic should be displayed first')
        self.assertEqual(response.context['evidences'][1][0], neutral)

        self.assertEqual(response.context['hypotheses'][0][0], self.hypotheses[1],
                         msg='Consistent hypotheses should be displayed first')
        self.assertEqual(response.context['hypotheses'][1][0], self.hypotheses[0])


class EvidenceDetailTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
        self.board = create_board('Test Board', days=5)
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc='Evidence #1',
            event_date=datetime.datetime.strptime('2010-06-01', '%Y-%m-%d').date(),
        )
        self.source = EvidenceSource.objects.create(
            evidence=self.evidence,
            source_url='https://google.com',
            source_date='2016-01-06',
            uploader=self.user,
            corroborating=True,
        )
        self.tags = [
            EvidenceSourceTag.objects.create(tag_name='Tag #1', tag_desc='Description for Tag #1'),
            EvidenceSourceTag.objects.create(tag_name='Tag #2', tag_desc='Description for Tag #2'),
        ]

    def test_evidence_detail_view(self):
        """Test that the evidence detail view renders reasonably."""
        response = self.client.get(reverse('openach:evidence_detail', args=(self.evidence.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/evidence_detail.html')
        self.assertContains(response, self.evidence.evidence_desc)
        self.assertContains(response, self.source.source_url)
        self.assertContains(response, self.board.board_title)
        self.assertContains(response, 'Add Corroborating Source')
        self.assertContains(response, 'Add Conflicting Source')
        self.assertContains(response, 'Tag #1')
        self.assertContains(response, 'Tag #2')

    def test_display_comment_form_when_logged_in(self):
        """Test that the comment entry form is displayed when a user is logged in."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:evidence_detail', args=(self.evidence.id,)))
        self.assertContains(response, 'Add comment')

    def test_can_display_comments(self):
        """Test that comments are displayed even if the user is not logged in."""
        comment = Comment.objects.create(
            content_type=ContentType.objects.get_for_model(Evidence),
            object_pk=self.evidence.id,
            user=self.user,
            user_url='http://example.com/~frank/',
            comment='First post.',
            site=Site.objects.get_current(),
        )
        response = self.client.get(reverse('openach:evidence_detail', args=(self.evidence.id,)))
        self.assertContains(response, 'Comments')
        self.assertContains(response, comment.comment)

    def test_add_source_tag(self):
        """Test that a logged in user can tag a piece of evidence."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:tag_source', args=(self.evidence.id, self.source.id)), data={
            'tag': self.tags[0].tag_name
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(len(AnalystSourceTag.objects.all()), 0)

    def test_display_added_tags_with_count(self):
        """Test that source tags are displayed with a count of how many times the tag has been applied to the source."""
        AnalystSourceTag.objects.create(source=self.source, tagger=self.user, tag=self.tags[0], tag_date=timezone.now())
        response = self.client.get(reverse('openach:evidence_detail', args=(self.evidence.id,)))
        self.assertContains(response, self.tags[0].tag_name + ' x 1')

    def test_remove_source_tag_on_toggle(self):
        """Test that a logged in user can tag a piece of evidence."""
        self.client.login(username='john', password='johnpassword')
        tag = self.tags[0]
        response = self.client.post(reverse('openach:tag_source', args=(self.evidence.id, self.source.id)), data={
            'tag': tag.tag_name
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(AnalystSourceTag.objects.all()), 1)
        response = self.client.post(reverse('openach:tag_source', args=(self.evidence.id, self.source.id)), data={
            'tag': tag.tag_name
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(AnalystSourceTag.objects.all()), 0)

    def test_cannot_get_add_source_tag_page(self):
        """Test that a rouge client can't 'GET' the add source tag page."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:tag_source', args=(self.evidence.id, self.source.id)))
        self.assertEqual(response.status_code, 302)

    def test_cannot_view_removed_evidence(self):
        """Test that a user cannot view evidence details for evidence that has been marked as removed."""
        remove(self.evidence)
        response = self.client.get(reverse('openach:evidence_detail', args=(self.evidence.id,)))
        self.assertEqual(response.status_code, 404)


class AddEvidenceTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
        self.board = create_board('Test Board', days=5)
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc='Evidence #1',
            event_date=None,
        )
        self.follower = add_follower(self.board)

    def test_require_login_for_add_evidence(self):
        """Test that the user must be logged in to access the add evidence form."""
        response = self.client.get(reverse('openach:add_evidence', args=(self.board.id,)))
        self.assertEqual(response.status_code, 302)

    def test_add_evidence_show_form(self):
        """Test that the add evidence view renders in a reasonable way."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:add_evidence', args=(self.board.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/add_evidence.html')

        # the view should display the board name and description
        self.assertContains(response, self.board.board_title)
        self.assertContains(response, self.board.board_desc)
        self.assertContains(response, 'Return to Board')

    def test_add_evidence_submit(self):
        """Test that the evidence is added to the database when the user submits the form."""
        self.client.login(username='john', password='johnpassword')
        text = 'Test Hypothesis 3'
        response = self.client.post(reverse('openach:add_evidence', args=(self.board.id,)), data={
            'evidence_desc': text,
            'event_date': '1/1/2016',
            'source_url': 'https://google.com',
            'source_date': '1/1/2016',
            'corroborating': 'True',
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(len(Evidence.objects.filter(evidence_desc=text)), 0)

        sources = list(EvidenceSource.objects.filter(source_url='https://google.com'))
        self.assertEqual(len(sources), 1)
        self.assertTrue(sources[0].corroborating)

        self.assertTrue(follows(self.user, self.board))
        self.assertGreater(self.follower.notifications.unread().count(), 0)

    def test_validate_url_length(self):
        """Test that the form rejects long URLs (issue #58)."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:add_evidence', args=(self.board.id,)), data={
            'evidence_desc': 'Evidence Description',
            'event_date': '1/1/2016',
            'source_url': 'https://google.com/' + ('x' * URL_MAX_LENGTH),
            'source_date': '1/1/2016',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/add_evidence.html')

    def test_evidence_edit_form(self):
        """Test that form validation passes for reasonable input."""
        form = EvidenceForm({
            'evidence_desc': 'Evidence Description',
            'event_date': '1/1/2016',
        })
        self.assertTrue(form.is_valid())

    def test_can_show_edit_form(self):
        """Test that a logged in user can view the edit evidence form."""
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc='Evidence #1',
            event_date=None,
        )
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:edit_evidence', args=(self.evidence.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/edit_evidence.html')

    def test_edit_form_has_remove_button(self):
        """Test that the edit form includes a remove button for the evidence creator."""
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc='Evidence #1',
            event_date=None,
        )
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:edit_evidence', args=(self.evidence.id,)))
        self.assertContains(response, 'Remove Evidence', status_code=200)

    def test_can_submit_edit_form(self):
        """Test that the evidence edit form properly updates the evidence."""
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc='Evidence #1',
            event_date=None,
        )
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:edit_evidence', args=(self.evidence.id,)), data={
            'evidence_desc': 'Updated Evidence Description',
            'event_date': '1/2/2016',
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreaterEqual(len(Evidence.objects.filter(evidence_desc='Updated Evidence Description')), 1)
        self.assertFalse(follows(self.user, self.board))
        self.assertGreater(self.follower.notifications.unread().count(), 0)

    def test_can_remove_evidence(self):
        """Test that evidence can be marked as removed via the form."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:edit_evidence', args=(self.evidence.id,)), data={
            'remove': 'remove'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Evidence.objects.count(), 0)
        self.assertEqual(Evidence.all_objects.count(), 1)


class AddSourceTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
        self.board = create_board('Test Board', days=5)
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc='Evidence #1',
            event_date=None,
        )

    def test_require_login_for_add_source(self):
        """Test that the user must be logged in to access the add source form."""
        response = self.client.get(reverse('openach:add_source', args=(self.evidence.id,)))
        self.assertEqual(response.status_code, 302)

    def test_add_source_show_form(self):
        """Test that the add evidence form renders in a reasonable way."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:add_source', args=(self.evidence.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/add_source.html')

        # the view should display the evidence description
        self.assertContains(response, self.evidence.evidence_desc)
        self.assertContains(response, 'Add Corroborating Source')
        self.assertContains(response, 'Return to Evidence')

    def test_add_evidence_source_submit(self):
        """Test that the source is actually added to the database when the user submits the form."""
        self.client.login(username='john', password='johnpassword')
        url = 'https://google.com'

        for corroborating in [True, False]:
            response = self.client.post(reverse('openach:add_source', args=(self.evidence.id,)), data={
                'source_url': url,
                'source_date': '1/1/2016',
                'corroborating': str(corroborating),
            })
            self.assertEqual(response.status_code, 302)
            self.assertGreater(len(EvidenceSource.objects.filter(source_url=url)), 0)
            self.assertGreater(len(EvidenceSource.objects.filter(corroborating=corroborating)), 0)

    def test_add_conflicting_evidence_form(self):
        """Test that the form is for conflicting sources when ?kind=conflicting query parameter is supplied."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:add_source', args=(self.evidence.id,)) + '?kind=conflicting')
        self.assertContains(response, 'Add Conflicting Source')

    def test_retain_source_type_on_form_error(self):
        """Test that the form is for conflicting sources when user submits a invalid form without a query string."""
        self.client.login(username='john', password='johnpassword')
        url = 'https://google.com'
        response = self.client.post(reverse('openach:add_source', args=(self.evidence.id,)), data={
            # intentionally leave off the evidence_date
            'source_url': url,
            'corroborating': False,
        })
        self.assertContains(response, 'Add Conflicting Source', status_code=200)

    def test_reject_long_url(self):
        """Test the the add source form rejects long URLs (issue #58)."""
        form = EvidenceSourceForm({
            'source_url':  'https://google.com' + ('x' * URL_MAX_LENGTH),
            'source_date': '1/1/2016',
        })
        self.assertFalse(form.is_valid())

    def test_add_conflicting_evidence_source_form(self):
        """Test that the form validation passes for reasonable input."""
        form = EvidenceSourceForm({
            'source_url':  'https://google.com',
            'source_date': '1/1/2016',
            'corroborating': 'False',
        })
        self.assertTrue(form.is_valid())
        form = EvidenceSourceForm({
            'source_url':  'https://google.com',
            'source_date': '1/1/2016',
            'corroborating': 'True',
        })
        self.assertTrue(form.is_valid())

    def test_add_conflicting_evidence_source(self):
        """Test that a conflicting source can be added via the form."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:add_source', args=(self.evidence.id,)), data={
            'source_url':  'https://google.com',
            'source_date': '1/1/2016',
            'corroborating': 'False',
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(len(EvidenceSource.objects.filter(corroborating=False)), 0)
        self.assertEqual(len(EvidenceSource.objects.filter(corroborating=True)), 0)


class ProfileTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
        UserSettings.objects.create(user=self.user)
        self.other = User.objects.create_user('paul', 'mccartney@thebeatles.com', 'pualpassword')

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
        self.client.login(username='john', password='johnpassword')
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
        self.client.login(username='john', password='johnpassword')
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
        self.client.login(username='john', password='johnpassword')
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
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('profile', args=(self.user.id,)))
        self.assertTemplateUsed(response, 'boards/profile.html')
        self.assertContains(response, 'View All', count=1)
        self.assertContains(response, 'You have not created any boards.')
        self.assertContains(response, 'You have not contributed to any boards.')

    def test_private_notifications(self):
        """Test that the profile page shows up to 5 notifications."""
        for x in range(0, 10):
            notify.send(self.other, recipient=self.user, actor=self.other, verb='said hello {}'.format(x))
        self.client.login(username='john', password='johnpassword')
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
        self.client.login(username='john', password='johnpassword')
        response = self.client.post('/accounts/profile/', data={
            'digest_frequency':  str(DigestFrequency.weekly.key),
        })
        self.assertEqual(response.status_code, 200)
        self.user.settings.refresh_from_db()
        self.assertEqual(self.user.settings.digest_frequency, DigestFrequency.weekly.key)


def create_board(board_title, days):
    """Create a board with the given title and publishing date offset.

    :param board_title: the board title
    :param days: negative for boards published in the past, positive for boards that have yet to be published
    """
    time = timezone.now() + datetime.timedelta(days=days)
    return Board.objects.create(board_title=board_title, pub_date=time)


class IndexViewTests(TestCase):

    def test_can_access_request_context(self):
        """Test that the test environment is set up properly."""
        response = self.client.get(reverse('openach:index'))
        self.assertIsNotNone(response, msg='No response was generated for index view')
        self.assertIsNotNone(response.context, 'Context was not returned with index view response')

    def test_can_show_index_no_news(self):
        """Test that a reasonable message is displayed if there is no project news."""
        response = self.client.get(reverse('openach:index'))
        self.assertContains(response, 'No project news.')

    def test_do_not_show_future_news(self):
        """Test that the project news doesn't show news that's scheduled for release in the future."""
        ProjectNews.objects.create(
            content='Test news',
            pub_date=timezone.now() + datetime.timedelta(days=5)
        )
        response = self.client.get(reverse('openach:index'))
        self.assertContains(response, 'No project news.')

    def test_show_published_news(self):
        """Test that the index view shows published project news."""
        ProjectNews.objects.create(
            content='Test news',
            pub_date=timezone.now() + datetime.timedelta(days=-1)
        )
        response = self.client.get(reverse('openach:index'))
        self.assertContains(response, 'Test news')

    def test_index_view_with_a_past_board(self):
        """Test that board with a pub_date in the past should be displayed on the index page."""
        create_board(board_title='Past board.', days=-30)
        response = self.client.get(reverse('openach:index'))
        self.assertQuerysetEqual(
            response.context['latest_board_list'],
            ['<Board: Past board.>']
        )


class RobotsViewTests(TestCase):

    def test_can_render_robots_page(self):
        """Test that the robots.txt view returns a robots.txt that includes a sitemap."""
        response = self.client.get(reverse('robots'))
        self.assertTemplateUsed(response, 'robots.txt')
        self.assertContains(response, 'sitemap.xml', status_code=200)
        self.assertEqual(response['Content-Type'], 'text/plain')


class AboutViewTests(TestCase):

    address = 'abc123'

    def test_can_render_about_page(self):
        """Test that any user can view the about page."""
        setattr(settings, 'DONATE_BITCOIN_ADDRESS', None)
        response = self.client.get(reverse('openach:about'))
        self.assertIsNotNone(response)
        self.assertNotContains(response, 'Donate')

    def test_can_create_bitcoin_donation_link(self):
        """Test utility method for constructing Bitcoin links."""
        self.assertIsNone(bitcoin_donation_url(site_name='anything', address=''))
        self.assertIn('abc123', bitcoin_donation_url(site_name='anything', address=self.address))

    def test_can_generate_bitcoin_qrcode(self):
        """Test SVG QR Code generation."""
        setattr(settings, 'DONATE_BITCOIN_ADDRESS', self.address)
        response = self.client.get(reverse('openach:bitcoin_donate'))
        self.assertEqual(response.status_code, 200)
        # should probably also test for content type image/svg+xml here

    def test_can_render_about_page_with_donate(self):
        """Test that any user can view an about page with a donate link if a Bitcoin address is set."""
        setattr(settings, 'DONATE_BITCOIN_ADDRESS', self.address)
        response = self.client.get(reverse('openach:about'))
        self.assertIsNotNone(response)
        self.assertContains(response, 'Donate', status_code=200)
        self.assertContains(response, self.address, status_code=200)

    def test_no_privacy_policy(self):
        """Test that the privacy policy panel is not displayed if a URL is not set."""
        setattr(settings, 'PRIVACY_URL', None)
        response = self.client.get(reverse('openach:about'))
        self.assertNotContains(response, 'Privacy Policy', status_code=200)

    def test_privacy_policy(self):
        """Test that the privacy policy panel is displayed if a URL is set."""
        url = 'https://github.com/twschiller/open-synthesis/blob/master/PRIVACY.md'
        setattr(settings, 'PRIVACY_URL', url)
        response = self.client.get(reverse('openach:about'))
        self.assertContains(response, 'Privacy Policy', status_code=200)


class ConsensusTests(TestCase):

    def test_no_votes_has_no_consensus(self):
        """Test that consensus_vote() returns None if no votes have been cast."""
        self.assertIsNone(consensus_vote([]))

    def test_na_consensus_for_single_vote(self):
        """Test that consensus_vote() returns N/A if only a single N/A vote is cast"""
        self.assertEqual(consensus_vote([Eval.not_applicable]), Eval.not_applicable)

    def test_none_na_consensus_for_single_vote(self):
        """Test that consensus_vote() returns the evaluation if only a single vote is cast."""
        self.assertEqual(consensus_vote([Eval.consistent]), Eval.consistent)

    def test_equal_na_vs_non_na(self):
        """Test that consensus_vote() returns an evaluation when an equal number of N/A and non-N/A votes have been cast."""
        for vote in [Eval.very_inconsistent, Eval.neutral, Eval.very_consistent]:
            self.assertEqual(consensus_vote([vote, Eval.not_applicable]), vote)
            self.assertEqual(consensus_vote([Eval.not_applicable, vote]), vote)

    def test_round_toward_neutral(self):
        """Test that consensus_vote() rounds the vote toward a neutral assessment."""
        self.assertEqual(consensus_vote([Eval.consistent, Eval.very_consistent]), Eval.consistent)
        self.assertEqual(consensus_vote([Eval.inconsistent, Eval.very_inconsistent]), Eval.inconsistent)


class EvidenceOrderingTests(TestCase):

    def test_mean_na_neutral_vote_maps_na_votes(self):
        """Test that mean_na_neutral_vote() maps N/A votes to neutral."""
        self.assertEqual(mean_na_neutral_vote([Eval.not_applicable]), Eval.neutral.value)
        self.assertEqual(mean_na_neutral_vote([Eval.not_applicable, Eval.very_inconsistent]), Eval.inconsistent.value)

    def test_mean_na_neutral_vote_only_maps_na_votes(self):
        """Test that mean_na_neutral_vote() does not map values other than N/A."""
        for x in Eval:
            if x is not Eval.not_applicable:
                self.assertEqual(mean_na_neutral_vote([x]), x.value)

    def test_no_hypotheses_has_zero_diagnosticity(self):
        """Test that diagnosticity() returns 0.0 when there are no votes."""
        self.assertEqual(diagnosticity([]), 0.0)

    def test_no_votes_has_zero_diagnosticity(self):
        """Test that diagnosticity() returns 0.0 when there are no votes."""
        self.assertEqual(diagnosticity([[], []]), 0.0)

    def test_different_more_diagnostic_than_neutral(self):
        """Test that diagnosticity() is higher for hypothesis with different consensus."""
        different = diagnosticity([[Eval.consistent], [Eval.inconsistent]])
        same = diagnosticity([[Eval.neutral], [Eval.neutral]])
        self.assertGreater(different, same)

    def test_evidence_sorting(self):
        """Test evidence sorting."""
        evidence_reverse = [
            [[Eval.not_applicable], [Eval.not_applicable]],  # n/a: 1.0, none: 0.0
            [[Eval.not_applicable], []],  # n/a: 0.5, none: 0.5
            [[Eval.neutral], [Eval.not_applicable]],  # n/a: 0.5, none: 0.0
            [[], []],
            [[Eval.neutral], []],
            [[Eval.neutral], [Eval.neutral]],
            [[Eval.very_consistent], [Eval.very_inconsistent]]
        ]
        in_order = sorted(evidence_reverse, key=evidence_sort_key)
        evidence_reverse.reverse()  # reverse in place
        self.assertListEqual(in_order, evidence_reverse)


class HypothesisOrderingTests(TestCase):

    def test_no_evidence_has_zero_inconsistency(self):
        """Test that inconsistency() returns 0.0 when there is no evidence."""
        self.assertEqual(inconsistency([]), 0.0)

    def test_consistent_evidence_has_zero_inconsistency(self):
        """Test that inconsistency() returns 0.0 when a evaluation is neutral or more consistent."""
        for vote in [Eval.neutral, Eval.consistent, Eval.very_consistent]:
            self.assertEqual(inconsistency([[vote]]), 0.0)

    def test_inconsistent_evidence_has_nonzero_inconsistency(self):
        """Test that inconsistency() returns more than 0.0 when a evaluation is neutral or more consistent."""
        for vote in [Eval.very_inconsistent, Eval.inconsistent]:
            self.assertGreater(inconsistency([[vote]]), 0.0)

    def test_very_inconsistent_implies_more_inconsistent(self):
        """Test that inconsistency() returns a higher value for a hypothesis that has an inconsistent rating."""
        h1 = inconsistency([[Eval.consistent], [Eval.inconsistent]])
        h2 = inconsistency([[Eval.very_inconsistent], [Eval.inconsistent]])
        self.assertLess(h1, h2)

    def test_inconsistency_assumptions(self):
        """Test basic inconsistency() behavior.

        (1) a hypothesis with 3 inconsistent ratings is less consistent than a hypothesis with 2 inconsistent ratings,
        regardless of whether N/A or Neutral is one of the other ratings.

        (2) a hypothesis with a very inconsistent rating is more inconsistent than a hypothesis with not just
        inconsistent ratings
        """
        h1 = inconsistency([[Eval.very_consistent], [Eval.not_applicable], [Eval.inconsistent], [Eval.inconsistent]])
        h2 = inconsistency([[Eval.inconsistent], [Eval.inconsistent], [Eval.neutral], [Eval.inconsistent]])
        h3 = inconsistency([[Eval.neutral], [Eval.not_applicable], [Eval.very_consistent], [Eval.very_inconsistent]])
        self.assertLess(h1, h2)
        self.assertLess(h2, h3)

    def test_calculate_na_proportion(self):
        """Test basic behavior of proportion_na()."""
        self.assertEqual(proportion_na([]), 0.0)
        self.assertEqual(proportion_na([[Eval.not_applicable]]), 1.0)
        self.assertEqual(proportion_na([[Eval.neutral]]), 0.0)
        self.assertEqual(proportion_na([[Eval.not_applicable], [Eval.not_applicable]]), 1.0)
        self.assertEqual(proportion_na([[Eval.not_applicable], []]), 0.5)
        self.assertEqual(proportion_na([[Eval.neutral], [Eval.not_applicable]]), 0.5)

    def test_calculate_unevaluated_proportion(self):
        """Test basic behavior of proportion_unevaluated()."""
        self.assertEqual(proportion_unevaluated([]), 0.0)
        self.assertEqual(proportion_unevaluated([[]]), 1.0)
        self.assertEqual(proportion_unevaluated([[Eval.not_applicable]]), 0.0)
        self.assertEqual(proportion_unevaluated([[]]), 1.0)
        self.assertEqual(proportion_unevaluated([[], [Eval.not_applicable]]), 0.5)

    def test_calculate_consistency(self):
        """Test basic behavior of consistency()."""
        self.assertEqual(consistency([]), 0.0)
        self.assertGreater(consistency([[Eval.very_consistent]]), consistency([[Eval.consistent]]))

    def test_hypothesis_sorting(self):
        """Test that we can sort hypotheses."""
        hypotheses_reverse = [
            [[Eval.very_inconsistent]],
            [[Eval.inconsistent]],
            [[Eval.not_applicable]],
            [[]],
            [[Eval.neutral]],
            [[Eval.consistent]],
            [[Eval.very_consistent]],
        ]
        in_order = sorted(hypotheses_reverse, key=hypothesis_sort_key)
        hypotheses_reverse.reverse()  # reverse in place
        self.assertListEqual(in_order, hypotheses_reverse)


class DisagreementTests(TestCase):

    def test_no_votes_returns_none(self):
        """Test that calc_disagreement() returns None when there is no votes"""
        self.assertEqual(calc_disagreement([]), None)

    def test_single_vote_has_zero_disagreement(self):
        """Test that calc_disagreement() returns 0.0 when there is a single vote."""
        for vote in Eval:
            self.assertEqual(calc_disagreement([vote]), 0.0)

    def test_same_vote_has_zero_disagreement(self):
        """Test that calc_disagreement() returns 0.0 when there are only votes of a single type."""
        for vote in Eval:
            self.assertEqual(calc_disagreement([vote, vote]), 0.0)

    def test_extreme_votes_have_greater_disagreement(self):
        """Test that votes that are further from neutral result in a larger disagreement score."""
        small = [Eval.consistent, Eval.inconsistent]
        large = [Eval.very_inconsistent, Eval.very_consistent]
        self.assertGreater(calc_disagreement(large), calc_disagreement(small))


class AccountManagementTests(TestCase):
    """Project-specific account management tests. General tests should be in the django-allauth library."""

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
        response = self.client.post('/accounts/signup/', data={
            'username': 'testuser',
            'email': None,
            'password1': 'testpassword1!',
            'password2': 'testpassword1!',
        })
        self.assertContains(response, 'Enter a valid email address.', status_code=200)

    def test_account_signup_flow(self):
        """Test that the user receives a confirmation email when they signup for an account with an email address."""
        setattr(settings, 'ACCOUNT_EMAIL_REQUIRED', True)
        response = self.client.post('/accounts/signup/', data={
            'username': 'testuser',
            'email': 'testemail@google.com',
            'password1': 'testpassword1!',
            'password2': 'testpassword1!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1, 'No confirmation email sent')
        # The example.com domain comes from django.contrib.sites plugin
        self.assertEqual(mail.outbox[0].subject, '[example.com] Please Confirm Your E-mail Address')
        self.assertListEqual(mail.outbox[0].to, ['testemail@google.com'])
        self.assertEqual(mail.outbox[0].from_email, DEFAULT_FROM_EMAIL)

    def test_settings_created(self):
        """Test that a settings object is created when the user is created."""
        setattr(settings, 'ACCOUNT_EMAIL_REQUIRED', False)
        self.client.post('/accounts/signup/', data={
            'username': 'testuser',
            'email': 'testemail@google.com',
            'password1': 'testpassword1!',
            'password2': 'testpassword1!',
        })
        user = User.objects.filter(username='testuser').first()
        self.assertIsNotNone(user.settings, 'User settings object not created')


class NotificationTests(TestCase):
    """Basic tests for notifications."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
        self.other = User.objects.create_user('paul', 'mccartney@thebeatles.com', 'pualpassword')
        self.board = Board.objects.create(
            board_title='Board Title',
            board_desc='Description',
            creator=self.user,
            pub_date=timezone.now(),
        )
        BoardFollower.objects.create(
            board=self.board,
            user=self.user,
        )

    def test_public_cannot_get_notifications(self):
        """Test that users that are not logged in cannot access the notifications list."""
        response = self.client.get(reverse('openach:notifications'))
        self.assertEqual(response.status_code, 302)

    def test_can_view_empty_notifications(self):
        """Test that a logged in user can view an empty notifications list."""
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:notifications'))
        self.assertContains(response, 'Notifications', status_code=200)

    def test_can_view_notifications(self):
        """Test that a logged in user can view one or more notifications."""
        notify.send(self.other, recipient=self.user, actor=self.other, verb='said hello!')
        notify.send(self.other, recipient=self.user, actor=self.other, verb='said hello again!')
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:notifications'))
        self.assertContains(response, 'paul said hello!', status_code=200)
        self.assertContains(response, 'paul said hello again!', status_code=200)

    def test_board_hypothesis_notifications(self):
        """Test the add/edit hypothesis notifications work render reasonably."""
        hypothesis = Hypothesis.objects.create(
            board=self.board,
            hypothesis_text='Hypothesis',
        )
        notify_add(self.board, self.other, hypothesis)
        notify_edit(self.board, self.other, hypothesis)
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:notifications'))
        self.assertContains(response, self.other.username, count=2)
        self.assertContains(response, self.board.board_title, count=2)
        self.assertContains(response, 'edited hypothesis', count=1)
        self.assertContains(response, 'added hypothesis', count=1)

    def test_board_evidence_notifications(self):
        """Test the add/edit evidence notifications work render reasonably."""
        evidence = Evidence.objects.create(
            board=self.board,
            evidence_desc='Evidence',
        )
        notify_add(self.board, self.other, evidence)
        notify_edit(self.board, self.other, evidence)
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:notifications'))
        self.assertContains(response, self.other.username, count=2)
        self.assertContains(response, self.board.board_title, count=2)
        self.assertContains(response, 'edited evidence', count=1)
        self.assertContains(response, 'added evidence', count=1)

    def test_can_clear_notifications(self):
        """Test that a user can clear notifications via POST request."""
        notify.send(self.other, recipient=self.user, actor=self.other, verb='said hello!')
        notify.send(self.user, recipient=self.other, actor=self.user, verb='said hello!')
        self.assertGreater(self.user.notifications.unread().count(), 0)
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:clear_notifications'), data={
            'clear': 'clear',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.user.notifications.unread().count(), 0)
        # make sure we didn't clear someone else's notifications
        self.assertGreater(self.other.notifications.unread().count(), 0)


class DigestTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.daily = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
        self.daily.date_joined = timezone.now() + datetime.timedelta(days=-2)
        self.daily.save()
        self.weekly = User.objects.create_user('paul', 'paul@thebeatles.com', 'paulpassword')
        self.weekly.date_joined = timezone.now() + datetime.timedelta(days=-2)
        self.weekly.save()
        UserSettings.objects.create(user=self.daily, digest_frequency=DigestFrequency.daily.key)
        UserSettings.objects.create(user=self.weekly, digest_frequency=DigestFrequency.weekly.key)

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


class SourceMetadataTestCase(TestCase):
    """Test cases for automatically fetching metadata from evidence sources."""

    def test_parse_open_graph_metadata(self):
        """Test that ``parse_metadata`` prefers open graph metadata."""
        html = """
            <html>
                <head>
                    <title>HTML title</title>
                    <meta name="description" content="HTML description">
                    <meta property="og:title" content="OG title">
                    <meta property="og:description" content="OG description">
                </head>
                <body></body>
            </html>
        """
        metadata = parse_metadata(html)
        self.assertEqual(metadata['title'], 'OG title')
        self.assertEqual(metadata['description'], 'OG description')

    def test_parse_html_metadata(self):
        """Test that ``parse_metadata`` falls back to html5 metadata."""
        html = """
            <html>
                <head>
                    <title>HTML title</title>
                    <meta name="description" content="HTML description">
                </head>
                <body></body>
            </html>
        """
        metadata = parse_metadata(html)
        self.assertEqual(metadata['title'], 'HTML title')
        self.assertEqual(metadata['description'], 'HTML description')

    def test_empty_metadata(self):
        """Test that ``parse_metadata`` doesn't crash on empty metadata."""
        html = """
            <html>
                <head></head>
                <body></body>
            </html>
        """
        metadata = parse_metadata(html)
        self.assertEqual(metadata.get('title', ''), '')
        self.assertEqual(metadata.get('description', ''), '')

    def test_fetch_source_metadata(self):
        """Test that ``fetch_source_metadata updates the source metadata"""
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
        board = create_board('Example Board', days=-1)
        evidence = Evidence.objects.create(
            board=board,
            evidence_desc='Example Evidence',
        )
        source = EvidenceSource.objects.create(
            evidence=evidence,
            source_url='http://www.example.com/index.html',
            source_date=timezone.now(),
            corroborating=True,
            uploader=self.user,
        )

        with patch('openach.tasks.requests.session') as session_mock:
            type(session_mock().get.return_value).status_code = PropertyMock(return_value=200)
            type(session_mock().get.return_value).text = PropertyMock(return_value="""
                <html>
                    <head>
                        <meta property="og:title" content="OG title">
                        <meta property="og:description" content="OG description">
                    </head>
                    <body></body>
                </html>
            """)
            fetch_source_metadata.delay(source.id)

        result = EvidenceSource.objects.get(pk=source.id)
        self.assertEqual(result.source_title, 'OG title')
        self.assertEqual(result.source_description, 'OG description')


class CeleryTestCase(TestCase):

    def test_celery_example(self):
        """Test that the ``example_task`` task runs with no errors, and returns the correct result."""
        result = example_task.delay(8, 8)

        self.assertEquals(result.get(), 16)
        self.assertTrue(result.successful())
