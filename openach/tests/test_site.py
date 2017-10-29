import datetime
from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from openach.models import ProjectNews
from openach.views import bitcoin_donation_url
from .common import create_board


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

