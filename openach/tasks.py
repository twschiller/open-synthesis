"""Celery tasks.

For more information, please see:
- http://docs.celeryproject.org/en/latest/django/first-steps-with-django.html

"""

import re
import logging
import requests

from bs4 import BeautifulSoup
from celery import shared_task  # noqa
from .models import EvidenceSource
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)


@shared_task
def example_task(x, y):  # pragma: no cover
    """Add two numbers together.

    An example for reference.
    """
    return x + y


@shared_task
def fetch_url_title_from_source(source_id):
    """
    Fetches Title and Description from a source 
    Source : https://github.com/erikriver/opengraph
    """
    source = EvidenceSource.objects.get(id=source_id)
    try:
        s = requests.Session()
        retries = Retry(total=5,
                        backoff_factor=0.1,
                        status_forcelist=[500, 502, 503, 504])
        s.mount('http://', HTTPAdapter(max_retries=retries))
        s.mount('https://', HTTPAdapter(max_retries=retries))
        html = s.get(source.source_url)
        doc = BeautifulSoup(html.text, "html.parser")
        ogs = doc.html.head.findAll(property=re.compile(r'^og'))
        url_info = {}
        for og in ogs:
            if og.has_attr('content'):
                url_info[og['property'][3:]] = og['content']
        if 'title' not in url_info:
            url_info['title'] = doc.title.text
            url_info['description'] = scrape_description(doc)
        source.source_title = url_info['title']
        source.source_description = url_info['description']
        logger.info(url_info)
        source.save()
    except requests.exceptions.ConnectionError as connection_exception:
        logger.info(connection_exception)
    except requests.exceptions.RequestException as request_exception:
        logger.info(request_exception)
    except Exception as e:
        logger.info(e)


def scrape_description(doc):
    tag = doc.html.head.findAll('meta', attrs={"name":"description"})
    result = "".join([t['content'] for t in tag])
    return result
