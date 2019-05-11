"""Celery tasks.

For more information, please see:
- http://docs.celeryproject.org/en/latest/django/first-steps-with-django.html

"""

import re
import logging
import requests

from bs4 import BeautifulSoup
from celery import shared_task
from .models import EvidenceSource
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

SOURCE_METADATA_RETRY = Retry(total=5, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])


@shared_task
def example_task(x, y):  # pragma: no cover
    """Add two numbers together.

    An example for reference.
    """
    return x + y


def parse_metadata(html):
    """Return document metadata from Open Graph, meta, and title tags.

    If title Open Graph property is not set, uses the document title tag. If the description Open Graph property is
    not set, uses the description meta tag.

    For more information, please see:
    - http://ogp.me/
    """
    # adapted from https://github.com/erikriver/opengraph
    metadata = {}
    doc = BeautifulSoup(html, "html.parser")
    tags = doc.html.head.findAll(property=re.compile(r'^og'))
    for tag in tags:
        if tag.has_attr('content'):
            metadata[tag['property'][len('og:'):]] = tag['content'].strip()

    if 'title' not in metadata and doc.title:
        metadata['title'] = doc.title.text.strip()

    if 'description' not in metadata:
        description_tags = doc.html.head.findAll('meta', attrs={'name': 'description'})
        # there should be at most one description tag per document
        if len(description_tags) > 0:
            metadata['description'] = description_tags[0].get('content', '').strip()

    return metadata


@shared_task
def fetch_source_metadata(source_id):
    """Fetch title and description metadata for the given source."""
    source = EvidenceSource.objects.get(id=source_id)
    session = requests.session()
    session.mount('http://', HTTPAdapter(max_retries=SOURCE_METADATA_RETRY))
    session.mount('https://', HTTPAdapter(max_retries=SOURCE_METADATA_RETRY))
    html = session.get(source.source_url)
    metadata = parse_metadata(html.text)
    source.source_title = metadata.get('title', '')
    source.source_description = metadata.get('description', '')
    source.save()
