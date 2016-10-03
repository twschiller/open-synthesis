"""Celery tasks.

For more information, please see:
- http://docs.celeryproject.org/en/latest/django/first-steps-with-django.html

"""

from celery import shared_task  # noqa


@shared_task
def example_task(x, y):
    """Add two numbers together.

    An example for reference.
    """
    return x + y
