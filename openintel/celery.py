"""Celery configuration.

For more information, please see:
- http://docs.celeryproject.org/en/latest/getting-started/first-steps-with-celery.html#first-steps-with-celery
- http://docs.celeryproject.org/en/latest/django/first-steps-with-django.html
- https://devcenter.heroku.com/articles/celery-heroku
"""

import os
import logging

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'openintel.settings')

from django.conf import settings  # noqa

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name
app = Celery('openintel')  # pylint: disable=invalid-name

app.conf.update(
    CELERY_TASK_SERIALIZER='json',
    CELERY_ACCEPT_CONTENT=['json'],  # Ignore other content
    CELERY_RESULT_SERIALIZER='json',
    # synchronously execute tasks, so you don't need to run a celery server
    # http://docs.celeryproject.org/en/latest/configuration.html#celery-always-eager
    CELERY_ALWAYS_EAGER=getattr(settings, 'CELERY_ALWAYS_EAGER', False),
)

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object('django.conf:settings')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

_BROKER_URL = getattr(settings, 'CELERY_BROKER_URL', None)
_BACKEND_URL = getattr(settings, 'CELERY_RESULT_BACKEND', _BROKER_URL)


if app.conf.CELERY_ALWAYS_EAGER:
    logger.warning('Running Celery tasks eagerly/synchronously; may impact performance')
    if _BROKER_URL or _BACKEND_URL:
        logger.warning('Ignoring Celery broker and result backend settings')
elif _BROKER_URL and _BACKEND_URL:
    logger.info('Celery Broker: %s', _BROKER_URL)
    logger.info('Celery Result Backend: %s', _BACKEND_URL)
    app.conf.update(BROKER_URL=_BROKER_URL, CELERY_RESULT_BACKEND=_BACKEND_URL)
else:
    logger.warning('No broker url/backend supplied for Celery; enable CELERY_ALWAYS_EAGER to run without a server')
