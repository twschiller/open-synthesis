import datetime

from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.urls import reverse
from django.utils import timezone
from django_comments.models import Comment

from openach.models import Evidence, Hypothesis, Evaluation, URL_MAX_LENGTH
from openach.views import EvidenceSource, EvidenceSourceTag, AnalystSourceTag, EvidenceForm

from .common import PrimaryUserTestCase, create_board, add_follower, remove


class AddEvidenceTests(PrimaryUserTestCase):

    def setUp(self):
        super().setUp()
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
        self.login()
        response = self.client.get(reverse('openach:add_evidence', args=(self.board.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/add_evidence.html')

        # the view should display the board name and description
        self.assertContains(response, self.board.board_title)
        self.assertContains(response, self.board.board_desc)
        self.assertContains(response, 'Return to Board')

    def test_add_evidence_submit(self):
        """Test that the evidence is added to the database when the user submits the form."""
        self.login()
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

        self.assertTrue(self.board.has_follower(self.user))
        self.assertGreater(self.follower.notifications.unread().count(), 0)

    def test_validate_url_length(self):
        """Test that the form rejects long URLs (issue #58)."""
        self.login()
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
        self.login()
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
        self.login()
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
        self.login()
        response = self.client.post(reverse('openach:edit_evidence', args=(self.evidence.id,)), data={
            'evidence_desc': 'Updated Evidence Description',
            'event_date': '1/2/2016',
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreaterEqual(len(Evidence.objects.filter(evidence_desc='Updated Evidence Description')), 1)
        self.assertFalse(self.board.has_follower(self.user))
        self.assertGreater(self.follower.notifications.unread().count(), 0)

    def test_can_remove_evidence(self):
        """Test that evidence can be marked as removed via the form."""
        self.login()
        response = self.client.post(reverse('openach:edit_evidence', args=(self.evidence.id,)), data={
            'remove': 'remove'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Evidence.objects.count(), 0)
        self.assertEqual(Evidence.all_objects.count(), 1)


class EvidenceDetailTests(PrimaryUserTestCase):

    def setUp(self):
        super().setUp()
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
        self.login()
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
        self.login()
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
        self.login()
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
        self.login()
        response = self.client.get(reverse('openach:tag_source', args=(self.evidence.id, self.source.id)))
        self.assertEqual(response.status_code, 302)

    def test_cannot_view_removed_evidence(self):
        """Test that a user cannot view evidence details for evidence that has been marked as removed."""
        remove(self.evidence)
        response = self.client.get(reverse('openach:evidence_detail', args=(self.evidence.id,)))
        self.assertEqual(response.status_code, 404)


class EvidenceAssessmentTests(PrimaryUserTestCase):

    def setUp(self):
        super().setUp()
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
        self.login()
        response = self.client.get(reverse('openach:evaluate', args=(self.board.id, self.evidence.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/evaluate.html')
        for hypothesis in self.hypotheses:
            self.assertContains(response, hypothesis.hypothesis_text)

    def test_evidence_assessment_form_submit(self):
        """Test that the evidence assessment form can handle a submit"""
        self.login()
        response = self.client.post(reverse('openach:evaluate', args=(self.board.id, self.evidence.id)), data={
            'hypothesis-{}'.format(self.hypotheses[0].id): '0',
            'hypothesis-{}'.format(self.hypotheses[1].id): '1'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Evaluation.objects.count(), 2, msg='Expecting 2 evaluation objects')
        self.assertTrue(self.board.has_follower(self.user))
