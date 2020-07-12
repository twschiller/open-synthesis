from django.test import TestCase
from django.urls import reverse

from openach.models import Evidence, Hypothesis
from openach.sitemap import BoardSitemap

from .common import PrimaryUserTestCase, create_board, remove


class SitemapTests(PrimaryUserTestCase):
    def setUp(self):
        super().setUp()
        self.board = create_board("Test Board", days=-5)
        self.evidence = Evidence.objects.create(
            board=self.board,
            creator=self.user,
            evidence_desc="Evidence #1",
            event_date=None,
        )
        self.hypotheses = [
            Hypothesis.objects.create(
                board=self.board, hypothesis_text="Hypothesis #1", creator=self.user,
            )
        ]

    def test_can_get_items(self):
        """Test that we can get all the boards."""
        sitemap = BoardSitemap()
        self.assertEqual(len(sitemap.items()), 1, "Sitemap included removed board")

    def test_cannot_get_removed_items(self):
        """Test that the sitemap doesn't include removed boards."""
        remove(self.board)
        sitemap = BoardSitemap()
        self.assertEqual(len(sitemap.items()), 0)

    def test_can_get_last_update(self):
        """Test that sitemap uses the latest change."""
        latest = Hypothesis.objects.create(
            board=self.board, hypothesis_text="Hypothesis #2", creator=self.user,
        )
        sitemap = BoardSitemap()
        board = sitemap.items()[0]
        self.assertEqual(sitemap.lastmod(board), latest.submit_date)


class RobotsViewTests(TestCase):
    def test_can_render_robots_page(self):
        """Test that the robots.txt view returns a robots.txt that includes a sitemap."""
        response = self.client.get(reverse("robots"))
        self.assertTemplateUsed(response, "robots.txt")
        self.assertContains(response, "sitemap.xml", status_code=200)
        self.assertEqual(response["Content-Type"], "text/plain")
