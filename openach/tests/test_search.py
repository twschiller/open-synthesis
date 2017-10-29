from django.test import TestCase
from django.urls import reverse

from .common import create_board


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
