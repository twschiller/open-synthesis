import datetime
from django.utils import timezone
from django.test import TestCase
from django.urls import reverse
from .models import Board


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


class BoardViewTests(TestCase):

    def test_index_view_with_a_past_board(self):
        """
        Board with a pub_date in the past should be displayed on the
        index page.
        """
        create_board(board_title="Past board.", days=-30)
        response = self.client.get(reverse('openach:index'))
        self.assertQuerysetEqual(
            response.context['latest_board_list'],
            ['<Board: Past board.>']
        )
