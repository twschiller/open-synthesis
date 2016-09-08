import datetime
from django.utils import timezone
from django.test import TestCase, Client
from django.urls import reverse
from .models import Board, Eval, Evidence, Hypothesis, Evaluation, ProjectNews
from .views import consensus_vote, diagnosticity, inconsistency, calc_disagreement, mean_na_neutral_vote
from .views import EvidenceSource, EvidenceSourceForm, EvidenceSourceTag, AnalystSourceTag
from django.contrib.auth.models import User
import logging
from django.core import mail
from unittest import skipUnless
from openintel.settings import ACCOUNT_EMAIL_REQUIRED, DEFAULT_FROM_EMAIL, SLUG_MAX_LENGTH
from .sitemap import BoardSitemap
from django_comments.models import Comment
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site


logger = logging.getLogger(__name__)


class BoardMethodTests(TestCase):

    def test_was_published_recently_with_future_board(self):
        """
        was_published_recently() should return False for board whose
        pub_date is in the future.
        """
        time = timezone.now() + datetime.timedelta(days=30)
        future_board = Board(pub_date=time)
        self.assertIs(future_board.was_published_recently(), False)

    def test_was_published_recently_with_old_question(self):
        """
        was_published_recently() should return False for boards whose
        pub_date is older than 1 day.
        """
        time = timezone.now() - datetime.timedelta(days=30)
        old_board = Board(pub_date=time)
        self.assertIs(old_board.was_published_recently(), False)

    def test_was_published_recently_with_recent_question(self):
        """
        was_published_recently() should return True for boards whose
        pub_date is within the last day.
        """
        time = timezone.now() - datetime.timedelta(hours=1)
        recent_board = Board(pub_date=time)
        self.assertIs(recent_board.was_published_recently(), True)

    def test_board_url_without_slug(self):
        """
        Smoke test to make sure we can grab the URL of a board that has no slug
        """
        self.assertIsNotNone(Board(id=1).get_absolute_url())

    def test_board_url_with_slug(self):
        """
        Smoke test to make sure we can grab the URL of a board that has a slug
        """
        slug = 'test-slug'
        self.assertTrue(slug in Board(id=1, board_slug=slug).get_absolute_url())


class BoardFormTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')

    def test_create_board_requires_login(self):
        """
        Test that the board creation form requires the user to be logged in
        """
        response = self.client.get(reverse('openach:create_board'))
        self.assertEqual(response.status_code, 302)

    def test_show_create_board_form(self):
        """
        Test that a logged in user can view the board creation form
        """
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:create_board'))
        self.assertTemplateUsed(response, 'boards/create_board.html')
        self.assertEqual(response.status_code, 200)

    def test_submit_valid_create_board(self):
        """
        Test that a logged in user can create a board via the form creation
        """
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:create_board'), data={
            'board_title': 'Test Board Title',
            'board_desc': 'Test Board Description',
            'hypothesis1': 'Test Hypotheses #1',
            'hypothesis2': 'Test Hypotheses #2',
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(len(Board.objects.filter(board_title='Test Board Title')), 0)
        self.assertGreater(len(Board.objects.filter(board_slug='test-board-title')), 0)

    def test_submit_valid_create_board_long_title(self):
        """
        Test that a user can create a board with a long name and that the slug will be truncated
        """
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:create_board'), data={
            'board_title': 'x' * (SLUG_MAX_LENGTH + 5),
            'board_desc': 'Test Board Description',
            'hypothesis1': 'Test Hypotheses #1',
            'hypothesis2': 'Test Hypotheses #2',
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(len(Board.objects.filter(board_slug='x' * SLUG_MAX_LENGTH)), 0)


class SitemapTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
        self.board = create_board('Test Board', days=5)
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc="Evidence #1",
            event_date=None,
            submit_date=timezone.now()
        )
        self.hypotheses = [
            Hypothesis.objects.create(
                board=self.board,
                hypothesis_text="Hypothesis #1",
                creator=self.user,
                submit_date=timezone.now(),
            ),
        ]

    def test_can_get_items(self):
        """ Test that we can get all the board """
        sitemap = BoardSitemap()
        self.assertEqual(len(sitemap.items()), 1)

    def test_can_get_last_update(self):
        """ Test that sitemap uses the latest change """
        latest = Hypothesis.objects.create(
            board=self.board,
            hypothesis_text="Hypothesis #2",
            creator=self.user,
            submit_date=timezone.now() + datetime.timedelta(days=5),
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
            evidence_desc="Evidence #1",
            event_date=None,
            submit_date=timezone.now()
        )
        self.hypotheses = [
            Hypothesis.objects.create(
                board=self.board,
                hypothesis_text="Hypothesis #1",
                creator=self.user,
                submit_date=timezone.now(),
            ),
            Hypothesis.objects.create(
                board=self.board,
                hypothesis_text="Hypothesis #2",
                creator=self.user,
                submit_date=timezone.now(),
            )
        ]

    def test_require_login_for_assessment(self):
        """
        Make sure that a user must be logged in to access the evidence evaluation screen
        """
        response = self.client.get(reverse('openach:evaluate', args=(self.board.id, self.evidence.id,)))
        self.assertEqual(response.status_code, 302)

    def test_evidence_assessment_form_renders(self):
        """
        Make sure the evidence assessment form renders in a reasonable way
        """
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:evaluate', args=(self.board.id, self.evidence.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/evaluate.html')
        for hypothesis in self.hypotheses:
            self.assertContains(response, hypothesis.hypothesis_text)

    def test_evidence_assessment_form_submit(self):
        """
        Make sure the evidence assessment form can handle a submit
        """
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:evaluate', args=(self.board.id, self.evidence.id)), data={
            'hypothesis-{}'.format(self.hypotheses[0].id): '0',
            'hypothesis-{}'.format(self.hypotheses[1].id): '1'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Evaluation.objects.count(), 2, msg="Expecting 2 evaluation objects")


class AddHypothesisTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
        self.board = create_board('Test Board', days=5)
        self.hypotheses = [
            Hypothesis.objects.create(
                board=self.board,
                hypothesis_text="Hypothesis #1",
                creator=self.user,
                submit_date=timezone.now(),
            ),
            Hypothesis.objects.create(
                board=self.board,
                hypothesis_text="Hypothesis #2",
                creator=self.user,
                submit_date=timezone.now()
            )
        ]

    def test_require_login_for_add_hypothesis(self):
        """
        Make sure that the user must be logged in to access the add hypothesis form
        """
        response = self.client.get(reverse('openach:add_hypothesis', args=(self.board.id,)))
        self.assertEqual(response.status_code, 302)

    def test_add_hypothesis_show_form(self):
        """
        Make sure the add hypothesis form renders in a reasonable way
        """
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
        """
        Make sure the hypothesis is actually added to the database when the user submits the form
        """
        self.client.login(username='john', password='johnpassword')
        text = 'Test Hypothesis 3'
        response = self.client.post(reverse('openach:add_hypothesis', args=(self.board.id,)), data={
            'hypothesis_text': text,
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(len(Hypothesis.objects.filter(hypothesis_text=text)), 0)


class BoardDetailTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
        self.board = create_board('Test Board', days=5)
        self.hypotheses = [
            Hypothesis.objects.create(
                board=self.board,
                hypothesis_text="Hypothesis #1",
                creator=self.user,
                submit_date=timezone.now(),
            ),
            Hypothesis.objects.create(
                board=self.board,
                hypothesis_text="Hypothesis #2",
                creator=self.user,
                submit_date=timezone.now(),
            )
        ]

    def _add_eval(self, hypothesis, user, eval):
        Evaluation.objects.create(
            board=self.board,
            hypothesis=hypothesis,
            evidence=self.evidence,
            user=user,
            value=eval.value
        )

    def _add_evidence(self):
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc="Evidence #1",
            event_date=None,
            submit_date=timezone.now()
        )

    def test_can_display_board_with_no_evidence(self):
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertEqual(response.status_code, 200)

        for hypothesis in self.hypotheses:
            self.assertContains(response, hypothesis.hypothesis_text)

    def test_can_display_board_with_no_assessments(self):
        self._add_evidence()
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.evidence.evidence_desc)

    def test_can_display_board_with_assessments_from_single_user(self):
        self._add_evidence()
        self._add_eval(self.hypotheses[0], self.user, Eval.consistent)
        self._add_eval(self.hypotheses[1], self.user, Eval.inconsistent)
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertContains(response, "Consistent", status_code=200)
        self.assertContains(response, "Inconsistent", status_code=200)

    def test_can_display_board_with_multiple_assessments(self):
        self._add_evidence()
        other = User.objects.create_user('paul', 'mccartney@thebeatles.com', 'paulpassword')
        self._add_eval(self.hypotheses[0], self.user, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], self.user, Eval.inconsistent)
        self._add_eval(self.hypotheses[0], other, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], other, Eval.consistent)
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertEqual(response.status_code, 200)

    def test_can_display_comments(self):
        comment = Comment.objects.create(
            content_type=ContentType.objects.get_for_model(Board),
            object_pk=self.board.id,
            user=self.user,
            user_url="http://example.com/~frank/",
            comment="First post.",
            site=Site.objects.get_current(),
        )
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertContains(response, "Comments")
        self.assertContains(response, comment.comment)

    def test_display_comment_form_when_logged_in(self):
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertContains(response, "Add comment")

    def test_do_not_display_comparison_button_when_logged_out(self):
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertNotContains(response, "Comparison")

    def test_display_comparison_button_when_logged_in(self):
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertContains(response, "Comparison")

    def test_can_display_disagreement_with_no_assessments(self):
        self._add_evidence()
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)) + "?view_type=disagreement")
        self.assertEqual(response.status_code, 200)

    def test_can_display_disagreement_with_multiple_assessments(self):
        self._add_evidence()
        other = User.objects.create_user('paul', 'mccartney@thebeatles.com', 'paulpassword')
        self._add_eval(self.hypotheses[0], self.user, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], self.user, Eval.very_consistent)
        self._add_eval(self.hypotheses[0], other, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], other, Eval.very_inconsistent)
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)) + "?view_type=disagreement")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Extreme Dispute")

    def test_can_display_comparison_no_assessments(self):
        self._add_evidence()
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)) + "?view_type=comparison")
        self.assertEqual(response.status_code, 200)

    def test_can_display_comparison(self):
        self._add_evidence()
        other = User.objects.create_user('paul', 'mccartney@thebeatles.com', 'paulpassword')
        self._add_eval(self.hypotheses[0], self.user, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], self.user, Eval.inconsistent)
        self._add_eval(self.hypotheses[0], other, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], other, Eval.consistent)
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)) + "?view_type=comparison")
        self.assertEqual(response.status_code, 200)


class EvidenceDetailTests(TestCase):

    def setUp(self):
        time = timezone.now()
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
        self.board = create_board('Test Board', days=5)
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc="Evidence #1",
            event_date=None,
            submit_date=time
        )
        self.source = EvidenceSource.objects.create(
            evidence=self.evidence,
            source_url="https://google.com",
            source_date="2016-01-06",
            uploader=self.user,
            submit_date=time,
            corroborating=True,
        )

    def test_evidence_detail_view(self):
        """
        Make sure that reasonable information is shown on the evidence detail form
        """
        response = self.client.get(reverse('openach:evidence_detail', args=(self.evidence.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/evidence_detail.html')
        self.assertContains(response, self.evidence.evidence_desc)
        self.assertContains(response, self.source.source_url)
        self.assertContains(response, self.board.board_title)
        self.assertContains(response, "Add Corroborating Source")
        self.assertContains(response, "Add Conflicting Source")

    def test_display_comment_form_when_logged_in(self):
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:evidence_detail', args=(self.evidence.id,)))
        self.assertContains(response, "Add comment")

    def test_can_display_comments(self):
        comment = Comment.objects.create(
            content_type=ContentType.objects.get_for_model(Evidence),
            object_pk=self.evidence.id,
            user=self.user,
            user_url="http://example.com/~frank/",
            comment="First post.",
            site=Site.objects.get_current(),
        )
        response = self.client.get(reverse('openach:evidence_detail', args=(self.evidence.id,)))
        self.assertContains(response, "Comments")
        self.assertContains(response, comment.comment)

    def test_add_source_tag(self):
        """
        Make sure that the user can tag a piece of evidence
        """
        self.client.login(username='john', password='johnpassword')
        tag = EvidenceSourceTag.objects.create(
            tag_name="Test Tag",
            tag_desc="Test Tag Description"
        )
        response = self.client.post(reverse('openach:tag_source', args=(self.evidence.id, self.source.id)), data={
            'tag': tag.tag_name
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(len(AnalystSourceTag.objects.all()), 0)

    def test_do_not_duplicate_source_tag(self):
        """
        Make sure that the user can tag a piece of evidence
        """
        self.client.login(username='john', password='johnpassword')
        tag = EvidenceSourceTag.objects.create(
            tag_name="Test Tag",
            tag_desc="Test Tag Description"
        )
        response = self.client.post(reverse('openach:tag_source', args=(self.evidence.id, self.source.id)), data={
            'tag': tag.tag_name
        })
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse('openach:tag_source', args=(self.evidence.id, self.source.id)), data={
            'tag': tag.tag_name
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(AnalystSourceTag.objects.all()), 1)

    def test_cannot_get_add_source_tag_page(self):
        """
        Make sure that a rouge client can't 'GET' the add source tag page
        """
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:tag_source', args=(self.evidence.id, self.source.id)))


class AddEvidenceTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
        self.board = create_board('Test Board', days=5)
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc="Evidence #1",
            event_date=None,
            submit_date=timezone.now()
        )

    def test_require_login_for_add_evidence(self):
        """
        Make sure that the user must be logged in to access the add evidence form
        """
        response = self.client.get(reverse('openach:add_evidence', args=(self.board.id,)))
        self.assertEqual(response.status_code, 302)

    def test_add_evidence_show_form(self):
        """
        Make sure the add evidence form renders in a reasonable way
        """
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:add_evidence', args=(self.board.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/add_evidence.html')

        # the view should display the board name and description
        self.assertContains(response, self.board.board_title)
        self.assertContains(response, self.board.board_desc)
        self.assertContains(response, "Return to Board")

    def test_add_evidence_submit(self):
        """
        Make sure the evidence is actually added to the database when the user submits the form
        """
        self.client.login(username='john', password='johnpassword')
        text = 'Test Hypothesis 3'
        response = self.client.post(reverse('openach:add_evidence', args=(self.board.id,)), data={
            'evidence_desc': text,
            'event_date': "1/1/2016",
            'evidence_url': "https://google.com",
            'evidence_date': "1/1/2016",
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(len(Evidence.objects.filter(evidence_desc=text)), 0)


class AddSourceTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')
        self.board = create_board('Test Board', days=5)
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc="Evidence #1",
            event_date=None,
            submit_date=timezone.now()
        )

    def test_require_login_for_add_source(self):
        """
        Make sure that the user must be logged in to access the add source form
        """
        response = self.client.get(reverse('openach:add_source', args=(self.evidence.id,)))
        self.assertEqual(response.status_code, 302)

    def test_add_source_show_form(self):
        """
        Make sure the add evidence form renders in a reasonable way
        """
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:add_source', args=(self.evidence.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/add_source.html')

        # the view should display the evidence description
        self.assertContains(response, self.evidence.evidence_desc)
        self.assertContains(response, "Add Corroborating Source")
        self.assertContains(response, "Return to Evidence")

    def test_add_evidence_source_submit(self):
        """
        Make sure the source is actually added to the database when the user submits the form
        """
        self.client.login(username='john', password='johnpassword')
        url = "https://google.com"
        response = self.client.post(reverse('openach:add_source', args=(self.evidence.id,)), data={
            'evidence_url': url,
            'evidence_date': "1/1/2016",
            'corroborating': True,
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(len(EvidenceSource.objects.filter(source_url=url)), 0)
        self.assertGreater(len(EvidenceSource.objects.filter(corroborating=True)), 0)

    def test_add_conflicting_evidence_form(self):
        """
        Make sure form is for conflicting sources when ?kind=conflicting query parameter is supplied
        """
        self.client.login(username='john', password='johnpassword')
        response = self.client.get(reverse('openach:add_source', args=(self.evidence.id,)) + "?kind=conflicting")
        self.assertContains(response, "Add Conflicting Source")

    def test_retain_source_type_on_form_error(self):
        """
        Make sure form is for conflict sources when user submits a malformed form without the query string
        """
        self.client.login(username='john', password='johnpassword')
        url = "https://google.com"
        response = self.client.post(reverse('openach:add_source', args=(self.evidence.id,)), data={
            # intentionally leave off the evidence_date
            'evidence_url': url,
            'corroborating': False,
        })
        self.assertContains(response, "Add Conflicting Source", status_code=200)

    def test_add_conflicting_evidence_source_form(self):
        """
        Sanity check for the EvidenceSourceForm
        """
        form = EvidenceSourceForm({
            'evidence_url':  "https://google.com",
            'evidence_date': "1/1/2016",
        })
        self.assertTrue(form.is_valid())
        form = EvidenceSourceForm({
            'evidence_url':  "https://google.com",
            'evidence_date': "1/1/2016",
            'corroborating': "True",
        })
        self.assertTrue(form.is_valid())

    def test_add_conflicting_evidence_source(self):
        """
        Make sure we can add a conflicting source via the form
        """
        self.client.login(username='john', password='johnpassword')
        response = self.client.post(reverse('openach:add_source', args=(self.evidence.id,)), data={
            'evidence_url':  "https://google.com",
            'evidence_date': "1/1/2016",
            'corroborating': "False",
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(len(EvidenceSource.objects.filter(corroborating=False)), 0)
        self.assertEqual(len(EvidenceSource.objects.filter(corroborating=True)), 0)


class ProfileTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('john', 'lennon@thebeatles.com', 'johnpassword')

    def test_view_public_activity(self):
        """
        Any user should be able to view a public profile
        """
        response = self.client.get(reverse('profile', args=(self.user.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User {}".format(self.user.username))


def create_board(board_title, days):
    """
    Creates a board with the given `board_title` and published the
    given number of `days` offset to now (negative for questions published
    in the past, positive for questions that have yet to be published).
    """
    time = timezone.now() + datetime.timedelta(days=days)
    return Board.objects.create(board_title=board_title, pub_date=time)


class IndexViewTests(TestCase):

    def test_can_access_request_context(self):
        """
        Smoke test to make sure the test environment is set up properly.
        """
        response = self.client.get(reverse('openach:index'))
        self.assertIsNotNone(response, msg="No response was generated for index view")
        self.assertIsNotNone(response.context, "Context was not returned with index view response")

    def test_can_show_index_no_news(self):
        """
        Show a reasonable message if there is no project news
        """
        response = self.client.get(reverse('openach:index'))
        self.assertContains(response, 'No project news.')

    def test_do_not_show_future_news(self):
        """
        Don't show project news that's scheduled to be released in the future
        """
        ProjectNews.objects.create(
            content='Test news',
            pub_date=timezone.now() + datetime.timedelta(days=5)
        )
        response = self.client.get(reverse('openach:index'))
        self.assertContains(response, 'No project news.')

    def test_show_published_news(self):
        """
        Show project news that has been published
        """
        ProjectNews.objects.create(
            content='Test news',
            pub_date=timezone.now() + datetime.timedelta(days=-1)
        )
        response = self.client.get(reverse('openach:index'))
        self.assertContains(response, 'Test news')

    def test_index_view_with_a_past_board(self):
        """
         Board with a pub_date in the past should be displayed on the index page.
        """
        create_board(board_title="Past board.", days=-30)
        response = self.client.get(reverse('openach:index'))
        self.assertQuerysetEqual(
            response.context['latest_board_list'],
            ['<Board: Past board.>']
        )


class RobotsViewTests(TestCase):

    def test_can_render_robots_page(self):
        """Check that the robots.txt view returns a robots.txt that includes a sitemap."""
        response = self.client.get(reverse('robots'))
        self.assertTemplateUsed(response, 'robots.txt')
        self.assertContains(response, 'sitemap.xml', status_code=200)
        self.assertEqual(response['Content-Type'], 'text/plain')


class AboutViewTests(TestCase):

    def test_can_render_about_page(self):
        """
        smoke test to make sure about route is working
        """
        response = self.client.get(reverse('openach:about'))
        self.assertIsNotNone(response)


class ConsensusTests(TestCase):

    def test_no_votes_has_no_consensus(self):
        """
        consensus_vote() should return None if no votes have been cast
        """
        self.assertIsNone(consensus_vote([]))

    def test_na_consensus_for_single_vote(self):
        """
        consensus_vote() should return N/A if only a single N/A vote is cast
        """
        self.assertEqual(consensus_vote([Eval.not_applicable]), Eval.not_applicable)

    def test_none_na_consensus_for_single_vote(self):
        """
        consensus_vote() should return the evaluation if only a single vote is cast
        """
        self.assertEqual(consensus_vote([Eval.consistent]), Eval.consistent)

    def test_equal_na_vs_non_na(self):
        """
        consensus_vote() should return an evaluation when an equal number of N/A and non-N/A votes have been cast
        """
        for vote in [Eval.very_inconsistent, Eval.neutral, Eval.very_consistent]:
            self.assertEqual(consensus_vote([vote, Eval.not_applicable]), vote)
            self.assertEqual(consensus_vote([Eval.not_applicable, vote]), vote)

    def test_round_toward_neutral(self):
        """
        consensus_vote() should round the vote toward a neutral assessment
        """
        self.assertEqual(consensus_vote([Eval.consistent, Eval.very_consistent]), Eval.consistent)
        self.assertEqual(consensus_vote([Eval.inconsistent, Eval.very_inconsistent]), Eval.inconsistent)


class DiagnosticityTests(TestCase):

    def test_mean_na_neutral_vote_maps_na_votes(self):
        """
        mean_na_neutral_vote() maps N/A votes to neutral
        """
        self.assertEqual(mean_na_neutral_vote([Eval.not_applicable]), Eval.neutral.value)
        self.assertEqual(mean_na_neutral_vote([Eval.not_applicable, Eval.very_inconsistent]), Eval.inconsistent.value)

    def test_mean_na_neutral_vote_only_maps_na_votes(self):
        """
        mean_na_neutral_vote() does not map values other than N/A
        """
        for x in Eval:
            if x is not Eval.not_applicable:
                self.assertEqual(mean_na_neutral_vote([x]), x.value)

    def test_no_hypotheses_has_zero_diagnosticity(self):
        """
        diagnosticity() should return 0.0 when there are no votes
        """
        self.assertEqual(diagnosticity([]), 0.0)

    def test_no_votes_has_zero_diagnosticity(self):
        """
        diagnosticity() should return 0.0 when there are no votes
        """
        self.assertEqual(diagnosticity([[], []]), 0.0)

    def test_different_more_diagnostic_than_neutral(self):
        """
        diagnosticity() should be higher for hypothesis with difference consensus than hypotheses with same consensus
        """
        different = diagnosticity([[Eval.consistent], [Eval.inconsistent]])
        same = diagnosticity([[Eval.neutral], [Eval.neutral]])
        self.assertGreater(different, same)


class InconsistencyTests(TestCase):

    def test_no_evidence_has_zero_inconsistency(self):
        """
        inconsistency() should return 0.0 when there is no evidence
        """
        self.assertEqual(inconsistency([]), 0.0)

    def test_consistent_evidence_has_zero_inconsistency(self):
        """
        inconsistency() should return 0.0 when a evaluation is neutral or more consistent
        """
        for vote in [Eval.neutral, Eval.consistent, Eval.very_consistent]:
            self.assertEqual(inconsistency([[vote]]), 0.0)

    def test_inconsistent_evidence_has_nonzero_inconsistency(self):
        """
        inconsistency() should return more than 0.0 when a evaluation is neutral or more consistent
        """
        for vote in [Eval.very_inconsistent, Eval.inconsistent]:
            self.assertGreater(inconsistency([[vote]]), 0.0)

    def test_very_inconsistent_implies_more_inconsistent(self):
        """
        inconsistency() should return higher value for hypothesis that has an inconsistent rating
        """
        h1 = inconsistency([[Eval.consistent], [Eval.inconsistent]])
        h2 = inconsistency([[Eval.very_inconsistent], [Eval.inconsistent]])
        self.assertLess(h1, h2)

    def test_inconsistency_assumptions(self):
        """
        Test a couple things: (1) a hypothesis with 3 inconsistent ratings is less consistent than a hypothesis with
        2 inconsistent ratings, regardless of whether N/A or Neutral is one of the other ratings. (2) a hypothesis with
        a very inconsistent rating is more inconsistent than a hypothesis with not just inconsistent ratings
        """
        h1 = inconsistency([[Eval.very_consistent], [Eval.not_applicable], [Eval.inconsistent], [Eval.inconsistent]])
        h2 = inconsistency([[Eval.inconsistent], [Eval.inconsistent], [Eval.neutral], [Eval.inconsistent]])
        h3 = inconsistency([[Eval.neutral], [Eval.not_applicable], [Eval.very_consistent], [Eval.very_inconsistent]])
        self.assertLess(h1, h2)
        self.assertLess(h2, h3)


class DisagreementTests(TestCase):

    def test_no_votes_returns_none(self):
        """
        calc_disagreement() should return None when there is no votes
        """
        self.assertEqual(calc_disagreement([]), None)

    def test_single_vote_has_zero_disagreement(self):
        """
        calc_disagreement() should return 0.0 when there is a single vote
        """
        for vote in Eval:
            self.assertEqual(calc_disagreement([vote]), 0.0)

    def test_same_vote_has_zero_disagreement(self):
        """
        calc_disagreement() should return 0.0 when there are only votes of a single type
        """
        for vote in Eval:
            self.assertEqual(calc_disagreement([vote, vote]), 0.0)

    def test_extreme_votes_have_greater_disagreement(self):
        """
        Test that votes that are further from neutral result in a larger disagreement score
        """
        small = [Eval.consistent, Eval.inconsistent]
        large = [Eval.very_inconsistent, Eval.very_consistent]
        self.assertGreater(calc_disagreement(large), calc_disagreement(small))


class AccountManagementTests(TestCase):
    """
    Project-specific account management tests. General tests should be in the django-allauth library
    """

    def test_can_show_signup_form(self):
        """
        Make sure we can render the basic signup form
        """
        response = self.client.get('/accounts/signup/')
        self.assertTemplateUsed('/account/email/signup.html')
        self.assertEqual(response.status_code, 200)

    @skipUnless(ACCOUNT_EMAIL_REQUIRED, reason="account email is not required.")
    def test_email_address_required(self):
        """
        Test that signup without email is rejected
        """
        response = self.client.post('/accounts/signup/', data={
            'username': 'testuser',
            'email': None,
            'password1': 'testpassword1!',
            'password2': 'testpassword1!',
        })
        self.assertContains(response, "Enter a valid email address.", status_code=200)

    def test_account_signup_flow(self):
        """
        Test that the user receives a confirmation email when they signup for an account with an email address
        """
        response = self.client.post('/accounts/signup/', data={
            'username': 'testuser',
            'email': 'testemail@google.com',
            'password1': 'testpassword1!',
            'password2': 'testpassword1!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1, "No confirmation email sent")
        # The example.com domain comes from django.contrib.sites plugin
        self.assertEqual(mail.outbox[0].subject, '[example.com] Please Confirm Your E-mail Address')
        self.assertListEqual(mail.outbox[0].to, ['testemail@google.com'])
        self.assertEqual(mail.outbox[0].from_email, DEFAULT_FROM_EMAIL)

