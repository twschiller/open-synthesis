from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.urls import reverse
from django.utils import timezone
from django_comments.models import Comment
from field_history.models import FieldHistory

from openach.models import Board, Evidence, Hypothesis, Evaluation, Eval, AuthLevels, BoardPermissions
from openach.forms import BoardForm

from .common import PrimaryUserTestCase, create_board, remove

SLUG_MAX_LENGTH = getattr(settings, 'SLUG_MAX_LENGTH')


class BoardFormTests(PrimaryUserTestCase):

    def test_create_board_requires_login(self):
        """Test that the board creation form requires the user to be logged in."""
        response = self.client.get(reverse('openach:create_board'))
        self.assertEqual(response.status_code, 302)

    def test_show_create_board_form(self):
        """Test that a logged in user can view the board creation form."""
        self.login()
        response = self.client.get(reverse('openach:create_board'))
        self.assertTemplateUsed(response, 'boards/create_board.html')
        self.assertEqual(response.status_code, 200)

    def test_submit_valid_create_board(self):
        """Test that a logged in user can create a board via the form creation."""
        self.login()
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
        self.assertTrue(board.has_follower(self.user))

    def test_submit_valid_create_board_long_title(self):
        """Test that a user can create a board with a long name and that the slug will be truncated."""
        self.login()
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
        board.permissions.make_public()
        self.login()
        response = self.client.get(reverse('openach:edit_board', args=(board.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boards/edit_board.html')
        self.assertNotContains(response, 'Remove Board')

    def test_staff_edit_form_has_remove_button(self):
        """Test that the edit form contains a remove button for staff."""
        board = Board.objects.create(board_title='Board #1', creator=self.user, pub_date=timezone.now())
        board.permissions.make_public()
        self.user.is_staff = True
        self.user.save()
        self.login()
        response = self.client.get(reverse('openach:edit_board', args=(board.id,)))
        self.assertContains(response, 'Remove Board', status_code=200)

    def test_board_meta_edit_permissions(self):
        """Test that with default permissions, the non-creator cannot edit the board permissions."""
        board = Board.objects.create(board_title='Board #1', creator=None, pub_date=timezone.now())
        self.login()
        response = self.client.get(reverse('openach:edit_board', args=(board.id,)))
        self.assertEqual(response.status_code, 403)

    def test_can_submit_edit_form(self):
        """Test that a logged in user can edit a board by submitting the form."""
        board = Board.objects.create(board_title='Board #1', creator=self.user, pub_date=timezone.now())
        board.permissions.make_public()

        # board initially has 3 changed fields: title, description, and if it has been removed
        self.assertEqual(FieldHistory.objects.get_for_model(board).count(), 3)

        response = self.client.get(reverse('openach:detail', args=(board.id,)))
        self.assertNotContains(response, 'Modify Permissions')

        self.login()

        response = self.client.get(reverse('openach:detail', args=(board.id,)))
        self.assertContains(response, 'Modify Permissions')

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
        board.permissions.make_public()
        self.user.is_staff = True
        self.user.save()
        self.login()
        response = self.client.post(reverse('openach:edit_board', args=(board.id,)), data={
            'remove': 'remove'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Board.objects.count(), 0)
        self.assertEqual(Board.all_objects.count(), 1)

    def test_non_owner_cannot_remove_board(self):
        """Test that a random user can't delete the board using a POST request."""
        board = Board.objects.create(board_title='Board #1', creator=None, pub_date=timezone.now())
        board.permissions.make_public()
        self.login()
        response = self.client.post(reverse('openach:edit_board', args=(board.id,)), data={
            'remove': 'remove'
        })
        self.assertEqual(response.status_code, 403)

    def test_can_view_board_history(self):
        """Test that the board history shows a change in board title and description."""
        board = Board.objects.create(board_title='Board #1', creator=self.user, pub_date=timezone.now())
        board.permissions.make_public()
        self.login()
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
        board.permissions.make_public()
        evidence = Evidence.objects.create(board=board, evidence_desc='Evidence')
        remove(evidence)
        response = self.client.get(reverse('openach:board_history', args=(board.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, evidence.evidence_desc)


class BoardDetailTests(PrimaryUserTestCase):

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

    def test_board_read_permission_without_creator(self):
        """Test that anonymous users cannot view board without creators when registration is required for board."""
        self.board.permissions.update_all(AuthLevels.registered)
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertEqual(response.status_code, 403)

    def test_board_read_permissions(self):
        """Test that only users with necessary permissions can access the board."""
        self.board.creator = self.user
        self.board.save()

        def expect_success():
            response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
            self.assertEqual(response.status_code, 200)

        def expect_fail():
            response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
            self.assertEqual(response.status_code, 403)

        # succeed b/c anyone can access
        self.board.permissions.update_all(AuthLevels.anyone)
        expect_success()

        # fail because user is not logged in
        self.board.permissions.update_all(AuthLevels.registered)
        expect_fail()

        # succeed because non-collaborator user is logged in
        self.login_other()
        expect_success()

        # fail because non-collaborator
        self.board.permissions.update_all(AuthLevels.collaborators)
        expect_fail()

        # add other user as collaborator
        self.board.permissions.collaborators.add(self.other)
        self.board.permissions.save()

        # succeed because user is now a collaborator
        expect_success()

        # fail because user is not creator
        self.board.permissions.update_all(AuthLevels.board_creator)
        expect_fail()

        # succeed because now logged in as creator
        self.login()
        expect_success()

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
        self._add_eval(self.hypotheses[0], self.user, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], self.user, Eval.inconsistent)
        self._add_eval(self.hypotheses[0], self.other, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], self.other, Eval.consistent)
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
        self.login()
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertContains(response, 'Add comment')

    def test_do_not_display_comparison_button_when_logged_out(self):
        """Test that the comparison view option is not displayed to anonymous users."""
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)))
        self.assertNotContains(response, 'Comparison')

    def test_display_comparison_button_when_logged_in(self):
        """Test that the comparison view option is displayed for logged in users."""
        self.login()
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
        self._add_eval(self.hypotheses[0], self.user, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], self.user, Eval.very_consistent)
        self._add_eval(self.hypotheses[0], self.other, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], self.other, Eval.very_inconsistent)
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)) + '?view_type=disagreement')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Extreme Dispute')

    def test_can_display_comparison_no_assessments(self):
        """Test that the comparison view renders when there are no assessments."""
        self._add_evidence()
        self.login()
        response = self.client.get(reverse('openach:detail', args=(self.board.id,)) + '?view_type=comparison')
        self.assertEqual(response.status_code, 200)

    def test_can_display_comparison(self):
        """Test that the comparison view renders when the user has provided assessments against a consensus."""
        self._add_evidence()
        self._add_eval(self.hypotheses[0], self.user, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], self.user, Eval.inconsistent)
        self._add_eval(self.hypotheses[0], self.other, Eval.inconsistent)
        self._add_eval(self.hypotheses[1], self.other, Eval.consistent)
        self.login()
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

        self.login()
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


class BoardListingTests(PrimaryUserTestCase):

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

    def test_user_public_board_view(self):
        """Test board listing for user that created a public board."""
        board = Board.objects.create(
            creator=self.user,
            board_title='Board Title',
            board_desc='Description',
            pub_date=timezone.now()
        )
        board.permissions.make_public()
        response = self.client.get(reverse('openach:user_boards', args=(self.user.id, ))+'?query=created')
        self.assertContains(response, 'Board Title', status_code=200)

    def test_user_hide_private_boards(self):
        board = Board.objects.create(
            creator=self.user,
            board_title='Board Title',
            board_desc='Description',
            pub_date=timezone.now(),
        )
        board.permissions.update_all(AuthLevels.collaborators)
        response = self.client.get(reverse('openach:user_boards', args=(self.user.id, ))+'?query=created')
        self.assertNotContains(response, 'Board Title', status_code=200)

class BoardEditPermissionsTests(PrimaryUserTestCase):

    def test_can_edit_board_permissions(self):
        """Test that the board owner can edit the board permissions via form."""
        board = Board.objects.create(
            creator=self.user,
            board_title='Board Title',
            board_desc='Description',
            pub_date=timezone.now()
        )
        self.login()
        response = self.client.post(reverse('openach:edit_permissions', args=(board.id, )), data={
            **{p: AuthLevels.registered.key for p in BoardPermissions.PERMISSION_NAMES},
            'collaborators': [],
        })
        self.assertEqual(response.status_code, 302)

        board.permissions.refresh_from_db()

        for p in BoardPermissions.PERMISSION_NAMES:
            self.assertEqual(getattr(board.permissions, p), AuthLevels.registered.key, f'failed for: {p}')

    def test_edit_permissions_permission(self):
        board = create_board('Board Title')
        board.permissions.update_all(AuthLevels.board_creator)
        self.login()
        response = self.client.post(reverse('openach:edit_permissions', args=(board.id, )))
        self.assertEqual(response.status_code, 403)
