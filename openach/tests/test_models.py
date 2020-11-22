import datetime

from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError

from openach.models import Board

from openach.tests.common import PrimaryUserTestCase, remove


class RemovableModelManagerTests(TestCase):
    def test_objects_does_not_include_removed(self):
        """Test that after an object is marked as removed, it doesn't appear in the query set."""
        board = Board.objects.create(
            board_title="Title", board_desc="Description", pub_date=timezone.now()
        )
        self.assertEqual(Board.objects.count(), 1)
        remove(board)
        self.assertEqual(Board.objects.count(), 0)
        self.assertEqual(Board.all_objects.count(), 1)


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
        slug = "test-slug"
        self.assertTrue(slug in Board(id=1, board_slug=slug).get_absolute_url())

class BoardTitleTests(PrimaryUserTestCase):
    def test_board_title_special_characters(self):
        """Test to make sure certain characters are allowed/disallowed in titles."""
        board = Board(
            board_desc="Test Board Description",
            creator=self.user,
            pub_date=timezone.now(),
        )
        fail_titles = [
            "Test Board Title!",
            "Test Board @ Title",
            "Test #Board Title",
            "Test Board Title++++",
        ]
        for title in fail_titles:
            board.board_title = title
            self.assertRaises(ValidationError, board.full_clean)

        pass_titles = [
            "Test Böard Titlé",
            "Test (Board) Title?",
            "Test Board & Title",
            "Test Board/Title",
        ]
        for title in pass_titles:
            board.board_title = title
            board.full_clean()