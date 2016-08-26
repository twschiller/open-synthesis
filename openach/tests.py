import datetime
from django.utils import timezone
from django.test import TestCase
from django.urls import reverse
from .models import Board, Eval
from .views import consensus_vote, diagnosticity, inconsistency


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

    def test_no_hypotheses_has_zero_diagnosticity(self):
        """
        diagnosticity() should return 0.0 when there are no votes
        """
        self.assertEqual(diagnosticity([]), 0.0)

    def test_no_votes_has_zero_diagnosticity(self):
        """
        diagnosticity() should return 0.0 when there are no votes
        """
        self.assertEqual(diagnosticity([{}, {}]), 0.0)

    def test_different_more_diagnostic_than_neutral(self):
        """
        diagnosticity() should be higher for hypothesis with difference consensus than hypotheses with same consensus
        """
        different = diagnosticity([{Eval.consistent}, {Eval.inconsistent}])
        same = diagnosticity([{Eval.neutral}, {Eval.neutral}])
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
            self.assertEqual(inconsistency([{vote}]), 0.0)

    def test_inconsistent_evidence_has_nonzero_inconsistency(self):
        """
        inconsistency() should return more than 0.0 when a evaluation is neutral or more consistent
        """
        for vote in [Eval.very_inconsistent, Eval.inconsistent]:
            self.assertGreater(inconsistency([{vote}]), 0.0)
