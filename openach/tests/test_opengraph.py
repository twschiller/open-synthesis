from django.utils import timezone
from unittest.mock import patch, PropertyMock

from openach.models import Evidence, EvidenceSource
from openach.tasks import parse_metadata, fetch_source_metadata

from .common import PrimaryUserTestCase, create_board


class SourceMetadataTestCase(PrimaryUserTestCase):
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
